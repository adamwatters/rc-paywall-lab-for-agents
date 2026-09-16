//  Loader.swift — rc-paywall-lab iOS harness.
//
//  Reads what `lab.py render` writes into <resources>/: qa/offerings.json (SDK wire
//  shape: offerings[].paywall_components + ui_config) and products.json, builds mock
//  SK1 products, and assembles an `Offering` with its paywall components attached —
//  the same construction the Android harness does. CDN image hosts are rewritten to
//  the local asset mirror when one exists.
//
//  Originally adapted from RevenueCat's PaywallPreviewResourcesLoader (purchases-ios,
//  Tests/RevenueCatUITests/PaywallsV2, MIT © RevenueCat Inc.).
//
//  SDK surface used (see docs/platforms.md for the compat matrix):
//    public:          Offering(identifier:serverDescription:paywallComponents:availablePackages:webCheckoutUrl:)
//                     Package(identifier:packageType:storeProduct:offeringIdentifier:webCheckoutUrl:)
//                     StoreProduct(sk1Product:)
//    @_spi(Internal): PaywallComponentsData, UIConfig (Decodable), Offering.PaywallComponents(uiConfig:data:)
//    @testable:       JSONDecoder.default (the SDK's snake_case decoder), Package.packageType(from:)
//  Why not OfferingsFactory: since purchases-ios 5.81.1 an OfferingsResponse no longer
//  carries decoded paywall_components (the SDK fetches them separately), so a factory-built
//  offering renders the fallback paywall. Decoding the components here also makes a
//  decode failure visible on screen ("Load failed: …") instead of a silent fallback.
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
    case noOfferingWithComponents
    case missingUIConfig
    case couldNotReadProducts
}

/// Minimal wire shape of qa/offerings.json (snake_case keys via JSONDecoder.default).
private struct LabOfferingsFile: Decodable {
    struct Offering: Decodable {
        let identifier: String
        let description: String?
        let paywallComponents: PaywallComponentsData?
    }
    let offerings: [Offering]
    let uiConfig: UIConfig?
}

class PaywallPreviewResourcesLoader {
    private var baseResourcesURL: URL
    private var offerings: [String: Offering] = [:]

    init(baseResourcesURL: URL) throws {
        self.baseResourcesURL = baseResourcesURL
        self.offerings = try loadOfferings()
    }

    var allOfferings: [Offering] { Array(offerings.values) }

    private func loadPackages(offeringIdentifier: String) throws -> [Package] {
        let url = baseResourcesURL.appendingPathComponent("products.json")
        guard let data = try? Data(contentsOf: url),
              let spec = try? JSONDecoder().decode(LabProducts.self, from: data) else {
            throw PaywallPreviewResourcesError.couldNotReadProducts
        }
        return spec.packages.map { p in
            Package(identifier: p.identifier,
                    packageType: Package.packageType(from: p.identifier),
                    storeProduct: StoreProduct(sk1Product: LabTrialProduct(spec: p)),
                    offeringIdentifier: offeringIdentifier,
                    webCheckoutUrl: nil)
        }
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

        for resourceURL in resourceDirectories {
            let offeringsPath = resourceURL.appendingPathComponent("offerings.json")
            guard let offeringsRawString = try? String(contentsOf: offeringsPath, encoding: .utf8) else { continue }

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
            let file: LabOfferingsFile
            do {
                file = try JSONDecoder.default.decode(LabOfferingsFile.self, from: modifiedData)
            } catch {
                print("LAB decode error: \(error)")
                throw PaywallPreviewResourcesError.failedToDecodeOfferings("\(error)")
            }
            guard let uiConfig = file.uiConfig else {
                throw PaywallPreviewResourcesError.missingUIConfig   // lab.py render always writes one
            }
            for off in file.offerings {
                guard let components = off.paywallComponents else {
                    print("LAB offering \(off.identifier): no paywall_components, skipped")
                    continue
                }
                let packages = try loadPackages(offeringIdentifier: off.identifier)
                print("LAB offering \(off.identifier): packages=\(packages.count) revision=\(components.revision)")
                result[off.identifier] = Offering(
                    identifier: off.identifier,
                    serverDescription: off.description ?? "",
                    paywallComponents: .init(uiConfig: uiConfig, data: components),
                    availablePackages: packages,
                    webCheckoutUrl: nil
                )
            }
        }
        if result.isEmpty {
            throw PaywallPreviewResourcesError.noOfferingWithComponents
        }
        return result
    }
}
