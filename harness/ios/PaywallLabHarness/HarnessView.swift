//  HarnessView.swift — rc-paywall-lab iOS harness.
//
//  Renders the offering in <resources>/qa/offerings.json full-bleed with RevenueCatUI
//  (the exact SDK version pinned in the Xcode project), with intro-offer eligibility
//  injected, and floating lab controls that can be tucked away for clean screenshots.
//
//  Launch environment (set via `xcrun simctl launch` with SIMCTL_CHILD_ prefix):
//    PAYWALL_LAB_RESOURCES  – absolute path to the rendered resources dir (required)
//    PAYWALL_LAB_ELIGIBLE   – "0" = trial-used / intro-ineligible (default eligible)
//    PAYWALL_LAB_CONTROLS   – "0" = start with controls hidden
//
//  Internals reached via @testable/@_spi imports: PaywallView(configuration:) with a
//  forced TrialOrIntroEligibilityChecker and a mock purchase handler. Both imports need
//  @_spi(Internal) — the eligibility checker is SPI-public.
//  Version notes (see docs/platforms.md compat matrix): PaywallViewConfiguration dropped
//  its `customerInfo:` parameter in purchases-ios 5.86.0.
import SwiftUI
@_spi(Internal) @testable import RevenueCat
@_spi(Internal) @testable import RevenueCatUI

struct HarnessView: View {
    static let resourcesPath = ProcessInfo.processInfo.environment["PAYWALL_LAB_RESOURCES"]

    @State var offerings: [Offering] = []
    @State var introEligible = ProcessInfo.processInfo.environment["PAYWALL_LAB_ELIGIBLE"] != "0"
    @State var controlsVisible = ProcessInfo.processInfo.environment["PAYWALL_LAB_CONTROLS"] != "0"
    @State var reloadToken = UUID()
    @State var loadError: String?

    var body: some View {
        ZStack(alignment: .top) {
            paywall.ignoresSafeArea()
            controls
        }
        .onAppear { load() }
    }

    @ViewBuilder private var paywall: some View {
        if let offering = offerings.first {
            PaywallView(configuration: .init(
                offering: offering,
                mode: .default,
                fonts: DefaultPaywallFontProvider(),
                introEligibility: .producing(eligibility: introEligible ? .eligible : .ineligible),
                purchaseHandler: .mock(preferredLocaleOverride: nil)
            ))
            .id("\(reloadToken)-\(introEligible)")
        } else {
            VStack {
                Spacer()
                Text(loadError ?? "No offering loaded").font(.footnote).foregroundStyle(.secondary).padding()
                Spacer()
            }
            .frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder private var controls: some View {
        if controlsVisible {
            HStack(spacing: 10) {
                Picker("Eligibility", selection: $introEligible) {
                    Text("Intro eligible").tag(true)
                    Text("Trial used").tag(false)
                }.pickerStyle(.segmented)
                Button("Reload") { load() }.buttonStyle(.borderless)
                Button { withAnimation(.snappy) { controlsVisible = false } } label: {
                    Image(systemName: "chevron.up.circle.fill").foregroundStyle(.secondary)
                }.buttonStyle(.borderless)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .shadow(color: .black.opacity(0.15), radius: 8, y: 2)
            .padding(.horizontal, 12)
        } else {
            HStack {
                Spacer()
                Button { withAnimation(.snappy) { controlsVisible = true } } label: {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.secondary).padding(9)
                        .background(.ultraThinMaterial, in: Circle())
                        .shadow(color: .black.opacity(0.15), radius: 6, y: 2)
                }.padding(.trailing, 10)
            }
        }
    }

    private func load() {
        guard let path = Self.resourcesPath else {
            loadError = "PAYWALL_LAB_RESOURCES not set — launch via `lab.py preview`"
            return
        }
        let url = URL(fileURLWithPath: path, isDirectory: true)
        do {
            let loader = try PaywallPreviewResourcesLoader(baseResourcesURL: url)
            offerings = loader.allOfferings.sorted { $0.identifier < $1.identifier }
            reloadToken = UUID()
            loadError = offerings.isEmpty ? "Loaded 0 offerings from \(path)" : nil
        } catch {
            offerings = []
            loadError = "Load failed: \(error)"
            print("PAYWALL LAB LOAD ERROR: \(error)")
        }
    }
}
