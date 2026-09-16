// rc-paywall-lab Android harness.
//
// Renders the offering in <resources>/qa/offerings.json with the stock RevenueCatUI
// Paywall composable (the SDK version pinned in app/build.gradle.kts), using ONLY
// public opt-in APIs: decode paywall components + ui_config with the SDK's own
// serializable types, mock products with TestStoreProduct, build an Offering, render.
//
// Intro-offer eligibility on Android is a property of the product (a package is
// eligible when its product carries a free-trial pricing phase), so "trial used" is
// simply the same products without their trial phase — exactly how the SDK decides
// `intro_offer` rules in production.
//
// Resources arrive over HTTP from the host (the emulator can't read host files):
// `lab.py preview` serves my/.resources on 127.0.0.1 and passes
//   --es resources http://10.0.2.2:<port>/   --ez eligible true|false   --ez controls true|false
@file:OptIn(InternalRevenueCatAPI::class, ExperimentalSerializationApi::class)

package dev.paywalllab.harness

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.revenuecat.purchases.InternalRevenueCatAPI
import com.revenuecat.purchases.LogLevel
import com.revenuecat.purchases.Offering
import com.revenuecat.purchases.Package
import com.revenuecat.purchases.PackageType
import com.revenuecat.purchases.PresentedOfferingContext
import com.revenuecat.purchases.Purchases
import com.revenuecat.purchases.PurchasesConfiguration
import com.revenuecat.purchases.UiConfig
import com.revenuecat.purchases.models.Period
import com.revenuecat.purchases.models.Price
import com.revenuecat.purchases.models.PricingPhase
import com.revenuecat.purchases.models.RecurrenceMode
import com.revenuecat.purchases.models.StoreProduct
import com.revenuecat.purchases.models.TestStoreProduct
import com.revenuecat.purchases.paywalls.components.common.PaywallComponentsData
import com.revenuecat.purchases.ui.revenuecatui.Paywall
import com.revenuecat.purchases.ui.revenuecatui.PaywallOptions
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.Json
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val base = (intent.getStringExtra("resources") ?: "http://10.0.2.2:8765/").trimEnd('/') + "/"
        val eligible = intent.getBooleanExtra("eligible", true)
        val controls = intent.getBooleanExtra("controls", true)
        if (!Purchases.isConfigured) {
            // The paywall view model needs a configured SDK instance to exist, but the offering is
            // supplied directly, so nothing real is fetched. The dummy key only produces
            // InvalidCredentials log lines. Nothing can be purchased.
            Purchases.logLevel = LogLevel.ERROR
            Purchases.configure(
                PurchasesConfiguration.Builder(applicationContext, "goog_paywall_lab_offline_harness").build()
            )
        }
        setContent { HarnessScreen(base, eligible, controls) }
    }
}

@Composable
fun HarnessScreen(base: String, eligibleDefault: Boolean, controlsDefault: Boolean) {
    var eligible by remember { mutableStateOf(eligibleDefault) }
    var controls by remember { mutableStateOf(controlsDefault) }
    var reload by remember { mutableIntStateOf(0) }
    var result by remember { mutableStateOf<Result<Offering>?>(null) }
    LaunchedEffect(eligible, reload) {
        result = withContext(Dispatchers.IO) { runCatching { ResourceLoader.load(base, eligible) } }
    }
    Box(Modifier.fillMaxSize()) {
        when (val r = result) {
            null -> Text("Loading…", Modifier.align(Alignment.Center))
            else -> r.fold(
                onSuccess = { offering ->
                    key(offering, eligible, reload) {
                        Paywall(PaywallOptions.Builder(dismissRequest = {}).setOffering(offering).build())
                    }
                },
                onFailure = { e -> Text("Load failed: $e", Modifier.align(Alignment.Center).padding(24.dp)) },
            )
        }
        Surface(
            modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(8.dp),
            shape = MaterialTheme.shapes.medium,
            tonalElevation = 4.dp,
            shadowElevation = 4.dp,
        ) {
            if (controls) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 6.dp)) {
                    FilterChip(selected = eligible, onClick = { eligible = true }, label = { Text("Intro eligible") })
                    FilterChip(selected = !eligible, onClick = { eligible = false }, label = { Text("Trial used") },
                        modifier = Modifier.padding(start = 6.dp))
                    TextButton(onClick = { reload++ }) { Text("Reload") }
                    TextButton(onClick = { controls = false }) { Text("Hide") }
                }
            } else {
                TextButton(onClick = { controls = true }) { Text("⚙") }
            }
        }
    }
}

object ResourceLoader {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    private fun get(url: String): String? {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = 5000; c.readTimeout = 10000
        return try { if (c.responseCode == 200) c.inputStream.bufferedReader().readText() else null } finally { c.disconnect() }
    }

    fun load(base: String, eligible: Boolean): Offering {
        var raw = get(base + "qa/offerings.json") ?: error("no offerings.json at $base (is lab.py's server running?)")
        // Same rule as the iOS harness: rewrite CDN hosts only when a local mirror exists.
        if (get(base + "qa/pawwalls/") != null) {
            raw = raw.replace("https://assets.pawwalls.com", base + "qa/pawwalls/assets")
                .replace("https://icons.pawwalls.com", base + "qa/pawwalls/icons")
        }
        val root = JSONObject(raw)
        val offerings = root.getJSONArray("offerings")
        val off = (0 until offerings.length()).map { offerings.getJSONObject(it) }
            .firstOrNull { it.has("paywall_components") } ?: error("no offering with paywall_components")
        val data = json.decodeFromString<PaywallComponentsData>(off.getJSONObject("paywall_components").toString())
        val uiConfig = root.optJSONObject("ui_config")?.let { json.decodeFromString<UiConfig>(it.toString()) } ?: UiConfig()

        val products = JSONObject(get(base + "products.json") ?: error("no products.json")).getJSONArray("packages")
        val offeringId = off.getString("identifier")
        val ctx = PresentedOfferingContext(offeringId)
        val packages = (0 until products.length()).map { products.getJSONObject(it) }.map { p ->
            val id = p.getString("identifier")
            val type = PackageType.values().firstOrNull { it.identifier == id } ?: PackageType.CUSTOM
            Package(id, type, product(p, eligible, ctx), ctx)
        }
        return Offering(
            identifier = offeringId,
            serverDescription = off.optString("description", ""),
            metadata = emptyMap(),
            availablePackages = packages,
            paywallComponents = Offering.PaywallComponents(uiConfig = uiConfig, data = data),
        )
    }

    private fun period(o: JSONObject): Period {
        val unit = when (o.getString("unit").lowercase()) {
            "day" -> Period.Unit.DAY
            "week" -> Period.Unit.WEEK
            "year" -> Period.Unit.YEAR
            else -> Period.Unit.MONTH
        }
        val n = o.getInt("count")
        val iso = "P$n" + when (unit) { Period.Unit.DAY -> "D"; Period.Unit.WEEK -> "W"; Period.Unit.YEAR -> "Y"; else -> "M" }
        return Period(n, unit, iso)
    }

    /** Mock product from a products.json entry. Trial phase present only when eligible. */
    private fun product(p: JSONObject, eligible: Boolean, ctx: PresentedOfferingContext): StoreProduct {
        val price = p.getJSONObject("price")
        val currency = price.optString("currency", "USD")
        val android = p.optJSONObject("android")
        val productId = android?.optString("product_id")?.takeIf { it.isNotBlank() }
            ?: p.getString("identifier").trimStart('$')
        val trial = p.optJSONObject("trial")?.takeIf { eligible }?.let {
            PricingPhase(
                billingPeriod = period(it),
                recurrenceMode = RecurrenceMode.FINITE_RECURRING,
                billingCycleCount = 1,
                price = Price(amountMicros = 0, currencyCode = currency, formatted = "Free"),
            )
        }
        val name = p.optString("name", productId)
        return TestStoreProduct(
            id = productId, name = name, title = "$name (Paywall Lab)", description = name,
            price = Price(
                amountMicros = (price.getDouble("amount") * 1_000_000).toLong(),
                currencyCode = currency,
                formatted = price.optString("formatted", price.getDouble("amount").toString()),
            ),
            period = period(p.getJSONObject("period")),
            freeTrialPricingPhase = trial,
            presentedOfferingContext = ctx,
        )
    }
}
