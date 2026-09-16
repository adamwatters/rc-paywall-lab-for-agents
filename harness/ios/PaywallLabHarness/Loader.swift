//  Loader.swift — rc-paywall-lab iOS harness.
//
//  Adapted from RevenueCat's PaywallPreviewResourcesLoader (purchases-ios,
//  Tests/RevenueCatUITests/PaywallsV2, MIT © RevenueCat Inc.). Reads the SDK
//  wire-format offerings JSON that `lab.py render` writes, binds packages to mock
//  StoreKit products described by products.json, and rewrites CDN image hosts to
//  the local asset mirror when one exists.
import Foundation
import StoreKit
@_spi(Internal) @testable import RevenueCat
@_spi(Internal) @testable import RevenueCatUI

// MARK: - products.json

struct LabProducts: Decodable { let packages: [LabPackage] }
struct LabPackage: Decodable {
    let identifier: String
    let name: String
    let price: LabPrice
    let period: LabPeriod
    let trial: LabPeriod?
    let ios: LabIOS?
    var productId: String { ios?.product_id ?? String(identifier.drop(while: { $0 == "$" })) }
}
struct LabPrice: Decodable { let amount: Double; let currency: String; let formatted: String? }
struct LabPeriod: Decodable {
    let unit: String
    let count: Int
    var skUnit: SKProduct.PeriodUnit {
        switch unit.lowercased() {
        case "day": return .day
        case "week": return .week
        case "year": return .year
        default: return .month
        }
    }
}
struct LabIOS: Decodable { let product_id: String? }

/// SK1 mock product with a configurable billing period and an optional free-trial
/// introductory offer, so `intro_offer` overrides and eligibility injection behave
/// like real App Store products.
final class LabTrialProduct: SK1Product, @unchecked Sendable {

    final class Period: SKProductSubscriptionPeriod, @unchecked Sendable {
        let _unit: SKProduct.PeriodUnit
        let _numberOfUnits: Int
        init(unit: SKProduct.PeriodUnit, numberOfUnits: Int) {
            self._unit = unit
            self._numberOfUnits = numberOfUnits
        }
        override var unit: SKProduct.PeriodUnit { self._unit }
        override var numberOfUnits: Int { self._numberOfUnits }
    }

    final class TrialDiscount: SKProductDiscount, @unchecked Sendable {
        let _period: Period
        let _locale: Locale
        init(period: Period, locale: Locale) {
            self._period = period
            self._locale = locale
        }
        override var price: NSDecimalNumber { 0 }
        override var priceLocale: Locale { self._locale }
        override var paymentMode: SKProductDiscount.PaymentMode { .freeTrial }
        override var numberOfPeriods: Int { 1 }
        override var subscriptionPeriod: SKProductSubscriptionPeriod { self._period }
    }

    let spec: LabPackage
    let locale: Locale

    init(spec: LabPackage) {
        self.spec = spec
        let currency = spec.price.currency.uppercased()
        self.locale = Locale(identifier: currency == "USD" ? "en_US" : "en_US@currency=\(currency)")
    }

    override var price: NSDecimalNumber { NSDecimalNumber(value: self.spec.price.amount) }
    override var priceLocale: Locale { self.locale }
    override var localizedTitle: String { self.spec.name }
    override var subscriptionPeriod: SKProductSubscriptionPeriod? {
        Period(unit: self.spec.period.skUnit, numberOfUnits: self.spec.period.count)
    }
    override var introductoryPrice: SKProductDiscount? {
        guard let trial = self.spec.trial else { return nil }
        return TrialDiscount(period: Period(unit: trial.skUnit, numberOfUnits: trial.count), locale: self.locale)
    }
}

// MARK: - Loader

enum PaywallPreviewResourcesError: Error {
    case noValidResourceDirectories
    case couldNotReadOfferingsFile
    case failedToConvertJSONToData
    case failedToDecodeOfferings(String)
    case couldNotParsePackagesData
    case failedToDecodePackages
    case couldNotReadProducts
}

class PaywallPreviewResourcesLoader {
    struct PackageData: Decodable {
        let packages: [OfferingsResponse.Offering.Package]
    }

    private var baseResourcesURL: URL
    private var offerings: [String: Offering] = [:]

    init(baseResourcesURL: URL) throws {
        self.baseResourcesURL = baseResourcesURL
        self.offerings = try loadOfferings()
    }

    var allOfferings: [Offering] { Array(offerings.values) }

    private func loadProducts() throws -> [String: StoreProduct] {
        let url = baseResourcesURL.appendingPathComponent("products.json")
        guard let data = try? Data(contentsOf: url),
              let spec = try? JSONDecoder().decode(LabProducts.self, from: data) else {
            throw PaywallPreviewResourcesError.couldNotReadProducts
        }
        var out: [String: StoreProduct] = [:]
        for p in spec.packages {
            out[p.productId] = .init(sk1Product: LabTrialProduct(spec: p))
        }
        return out
    }

    private func loadOfferings() throws -> [String: Offering] {
        var result: [String: Offering] = [:]
        let resourceDirectories = (try? FileManager.default.contentsOfDirectory(
            at: baseResourcesURL, includingPropertiesForKeys: [.isDirectoryKey], options: .skipsHiddenFiles
        ))?.filter { url in
            (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
        } ?? []
        if resourceDirectories.isEmpty {
            throw PaywallPreviewResourcesError.noValidResourceDirectories
        }
        let products = try loadProducts()
        let packagesPath = baseResourcesURL.appendingPathComponent("packages.json")

        for resourceURL in resourceDirectories {
            let resource = resourceURL.lastPathComponent
            let offeringsPath = resourceURL.appendingPathComponent("offerings.json")
            guard let offeringsRawString = try? String(contentsOf: offeringsPath) else { continue }

            // Rewrite CDN hosts only when a local mirror exists; else images load from the network.
            let mirror = resourceURL.appendingPathComponent("pawwalls")
            let modifiedJSON = FileManager.default.fileExists(atPath: mirror.path)
                ? offeringsRawString
                    .replacingOccurrences(of: "https://assets.pawwalls.com",
                                          with: mirror.appendingPathComponent("assets").absoluteString)
                    .replacingOccurrences(of: "https://icons.pawwalls.com",
                                          with: mirror.appendingPathComponent("icons").absoluteString)
                : offeringsRawString

            guard let modifiedData = modifiedJSON.data(using: .utf8) else {
                throw PaywallPreviewResourcesError.failedToConvertJSONToData
            }
            let offeringsResponse: OfferingsResponse
            do {
                offeringsResponse = try JSONDecoder.default.decode(OfferingsResponse.self, from: modifiedData)
            } catch {
                print("LAB decode error: \(error)")
                throw PaywallPreviewResourcesError.failedToDecodeOfferings("\(error)")
            }
            for off in offeringsResponse.offerings {
                print("LAB offering \(off.identifier): paywallComponents=\(off.paywallComponents != nil)",
                      "errors=\(String(describing: off.paywallComponents?.errorInfo))")
            }
            guard let packagesData = try? Data(contentsOf: packagesPath) else {
                throw PaywallPreviewResourcesError.couldNotParsePackagesData
            }
            guard let packages = try? JSONDecoder.default.decode(PackageData.self, from: packagesData) else {
                throw PaywallPreviewResourcesError.failedToDecodePackages
            }
            let offeringsWithPackages = offeringsResponse.offerings.map { offering in
                OfferingsResponse.Offering(
                    identifier: offering.identifier,
                    description: offering.description,
                    packages: packages.packages,
                    paywallComponents: offering.paywallComponents,
                    draftPaywallComponents: offering.draftPaywallComponents,
                    webCheckoutUrl: offering.webCheckoutUrl
                )
            }
            let response = OfferingsResponse(
                currentOfferingId: offeringsResponse.currentOfferingId,
                offerings: offeringsWithPackages,
                placements: offeringsResponse.placements,
                targeting: offeringsResponse.targeting,
                uiConfig: offeringsResponse.uiConfig ?? PreviewMock.uiConfig
            )
            let offerings = OfferingsFactory().createOfferings(
                from: products,
                contents: Offerings.Contents(response: response, httpResponseOriginalSource: .mainServer),
                loadedFromDiskCache: false
            )
            if let all = offerings?.all {
                result.merge(all) { _, new in new }
            }
        }
        return result
    }
}
