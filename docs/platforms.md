# Platforms, toolchains, SDK pins

Both harnesses take the same inputs (rendered `my/.resources/`, an eligibility flag) and
produce the same screenshots. Neither patches the SDK; each pins the SDK version in
**one line**, set by `python3 lab.py detect-sdk <app> --apply`.

## iOS — `harness/ios/`

- Hand-written Xcode project (no generators) with a remote SwiftPM dependency on
  `purchases-ios` at an exact version (`project.pbxproj`, `XCRemoteSwiftPackageReference`).
- Reaches SDK internals via `@_spi(Internal) @testable import RevenueCat` / `RevenueCatUI`
  (Debug builds with `ENABLE_TESTABILITY`): `PaywallView(configuration:)` with a forced
  `TrialOrIntroEligibilityChecker`, a mock purchase handler, `TestData.customerInfo`.
- Products are mocked as SK1 products from `products.json` (price, period, free trial).
- Reads the resources dir straight from the host filesystem (simulator processes can).
- **First build resolves the package from GitHub: a full clone of purchases-ios,
  ~1 GB, ~10 min, cached in `~/Library/Caches/org.swift.swiftpm`.** It looks hung. It isn't.
- Needs Xcode 16+ and an iOS 18.5+ simulator runtime (SDK min for the tester view).
  Derived data lives in `.build/ios/` (not /tmp, which macOS purges).

## Android — `harness/android/`

- Plain Gradle app (AGP 8.13, Kotlin 2.0, Compose BOM 2024.09) depending on
  `com.revenuecat.purchases:purchases-ui:<version>` from Maven Central
  (`app/build.gradle.kts`, `val revenueCatVersion`).
- **Public opt-in APIs only** (`@OptIn(InternalRevenueCatAPI::class)`): decodes
  `paywall_components` → `PaywallComponentsData` and `ui_config` → `UiConfig` with
  `Json { ignoreUnknownKeys; explicitNulls = false }`, mocks products with
  `TestStoreProduct`, builds an `Offering`, renders the stock `Paywall(options)`.
- Eligibility = product property: a package is intro-eligible when its product has a
  free-trial pricing phase. "Trial used" drops the phase. Same logic as production.
- The SDK must be configured to exist; a dummy `goog_` key is used and only logs
  `InvalidCredentialsError`. Nothing can be purchased.
- The emulator can't read host files, so `lab.py` serves `my/.resources/` on
  `127.0.0.1:<port>` and the app fetches from `http://10.0.2.2:<port>/` (manifest has
  `usesCleartextTraffic`). Intent extras: `--es resources`, `--ez eligible`, `--ez controls`.
- Emulator is cold-booted with `-no-snapshot-load` (a stale snapshot leaves the device
  "offline" forever) and headless by default (`android.headless` in config).
- Needs a JDK ≥ 17 (`lab.py` finds Homebrew's `openjdk@21/@17`, `/usr/libexec/java_home`,
  or a recent Android Studio JBR — note Studio versions before 2023 bundle JDK 11),
  the Android SDK (platform 36 is auto-installed by the Gradle plugin if licenses are
  accepted), and one AVD. First build ~5 min.

## SDK compatibility matrix

Verified = a real design rendered in both eligibility states on this harness.

| harness | SDK version | verified | notes |
|---|---|---|---|
| ios | purchases-ios 5.76.0 | 2026-09-16 | |
| android | purchases-android 10.8.0 | 2026-09-16 | |

Bumping: run `detect-sdk --apply` (or edit the one line), then `preview --build`. If a
build breaks (renamed internal, changed initializer), fix the harness and send a
prompt with the version and the error so the matrix grows.

## Cross-platform data rules (both harnesses, same JSON)

- Every image source needs all five URL fields (Android's decoder throws on missing
  `webp`/`webp_low_res`; iOS is lenient; the API requires all).
- Every `ui_config` font alias needs an `ios` and an `android` face.
- Render differences you'll see and shouldn't fix: system font (SF vs Roboto), toggle
  styling (iOS switch vs Material), safe-area insets.
