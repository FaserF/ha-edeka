<div align="center">
  <h1>EDEKA Offers (for Home Assistant) 🛒</h1>
  <p><strong>A secure, robust Home Assistant integration that fetches weekly offers and market status for your local EDEKA market directly from the official EDEKA Web API.</strong></p>

  [![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz)
  [![Downloads (Current release)](https://img.shields.io/github/downloads/FaserF/ha-edeka/latest/edeka.zip?label=Downloads%20(Current%20release)&style=for-the-badge)](https://github.com/FaserF/ha-edeka/releases)
  [![GitHub Release](https://img.shields.io/github/v/release/FaserF/ha-edeka?style=for-the-badge)](https://github.com/FaserF/ha-edeka/releases)
  [![License](https://img.shields.io/github/license/FaserF/ha-edeka?style=for-the-badge)](LICENSE)
</div>

---

## 🧭 Quick Links

| | | | |
| :--- | :--- | :--- | :--- |
| [✨ Features](#-features) | [📦 Installation](#-installation) | [⚙️ Configuration](#️-configuration) | [🛠️ Options](#️-options-flow) |
| [🧑‍💻 Development](#-development) | [💖 Credits](#-credits--acknowledgements) | [📄 License](#-license) | |

### Why use this integration?
Instead of scraping public HTML pages (which constantly break) or using generic web frames, this integration connects directly to the official EDEKA Web API. Using curl_cffi for browser impersonation, it fetches structured, high-fidelity offer and market data in real-time.

---

### 🛒 Supermarket Family & Deals Hub

Check out our full collection of Home Assistant supermarket integrations and the multi-store aggregator:

| Repository | Description |
| :--- | :--- |
| 🏷️ [**Grocery Deals (ha-grocery-deals)**](https://github.com/FaserF/ha-grocery-deals) | **Smart multi-store price comparison hub (aggregates all 5 integrations)** |
| 🔴 [**ha-rewe**](https://github.com/FaserF/ha-rewe) | REWE weekly offers, bonus points, coupons & product filters |
| 🔵 [**ha-lidl**](https://github.com/FaserF/ha-lidl) | Lidl Plus weekly offers, coupons & digital receipts |
| ⚪ [**ha-aldi**](https://github.com/FaserF/ha-aldi) | ALDI Süd & ALDI Nord weekly flyers & brochures |
| 🔴 [**ha-norma**](https://github.com/FaserF/ha-norma) | Norma weekly store discounts & flyer offers |

---

It groups all sensors under a single market device and implements advanced lock-serialisation, random jitter delays, and backoffs to keep your setup stable and prevent rate-limiting.

## ✨ Features

- **🛒 Offers Sensor**:
  - Reports the **number of current weekly discounted items** as its state.
  - Attributes include: `national` (`true` if nationwide fallback offers, `false` if local market flyer offers), titles, base prices, active discount prices, categories, and direct links to product images.

> [!WARNING]
> **Offers Limitation — Local Store Offers vs. National Fallback**
>
> - **Local Market Flyer Offers**: If an individual EDEKA merchant/franchise store has digitized their local weekly offers in the EDEKA Web API, all items (typically 100–300+ items) are returned and the sensor attribute `national` is set to `false`.
> - **National Fallback (20 items)**: Some independent merchants do not publish their local store flyers into the central web API. In this case, the EDEKA API returns `national: true` with a fallback set of exactly 20 nationwide campaign offers (the sensor's `national` attribute will be `true`).

- **📸 EDEKA / PAYBACK Loyalty Card QR Code Entity (`image`)**:
  - A dynamic 400x400 PNG QR Code entity rendering your EDEKA App / PAYBACK card barcode number for scanning directly at the checkout.
- **📱 Dedicated EDEKA Account Device**:
  - Grouped under a dedicated **EDEKA Account (DE)** device with direct link to your PAYBACK web portal.

> [!WARNING]
> **eBons (receipts) and Coupons are currently NOT supported.**
> EDEKA's personal data endpoints require an OAuth2 access token issued exclusively by the official EDEKA iOS/Android App (via Keycloak). The `KEYCLOAK_IDENTITY` web session cookie does **not** grant access to these endpoints. Until a compatible token exchange is discovered, those sensors will always show `0 items` / `Keine Kassenbons`.

- **🏪 Market Status Sensor** *(disabled by default)*:
  - Reports **Open / Closed** based on real-time business hours from the market's profile.
  - Attributes include: address, ZIP code, city, phone number, GPS coordinates, opening hours for all weekdays, and available in-store services (e.g. Payback, EDEKA App Coupons).
  - Works with all EDEKA market formats: **EDEKA Center (E-Center)**, **EDEKA Express / Xpress**, **EDEKA City Markt**, and standard regular/franchise stores.

> [!NOTE]
> The **Market Status Sensor** is disabled by default. Enable it in **Settings › Devices & Services › EDEKA › Entities** if you want to use it.

- **🔍 Location-Based Auto-Discovery**:
  - On startup, the integration automatically searches for nearby EDEKA markets based on your Home Assistant home location (ZIP code / city name).
  - If a market is found within the configured radius and not yet set up, a **discovery notification** will appear in the UI for easy one-click setup.

- **🛡️ Rate-Limiting & Anti-Ban Protections**:
  - **First-Fetch Optimisation**: Skips jitter sleep on initial setup so the first refresh completes instantly.
  - **Lock Queueing**: A domain-wide lock ensures concurrent updates (e.g., after a reboot) run sequentially.
  - **Random Jitter**: Introduces a 5–30 second delay between requests.
  - **Restart-Resistance**: Saves parsed data to HA storage cache to survive restarts without hitting the API. Re-fetches if market details are missing.
  - **Exponential Backoff**: Backs off for up to 24 hours on 403 or 429 errors.

- **⚙️ Device-Based Grouping**:
  - All sensors and button entities are automatically grouped under a main EDEKA Market device.
  - **Market Visit Button**: The device registry provides a dynamic configuration URL that takes you straight to your specific market's offers page.

- **🎛️ Manual Force Update** *(disabled by default)*:
  - A **Force Update** button entity allows manually triggering an API update on demand.

- **🔍 Diagnostic Downloads**:
  - Full support for Home Assistant UI Diagnostics with sensitive data automatically redacted.

## ❤️ Support This Project

> I maintain this integration in my **free time alongside my regular job** — debugging, building features, and keeping the API integration updated.
>
> **This project is and will always remain 100% free.**
>
> Donations are completely voluntary — but they help me stay motivated and dedicate more time to maintaining open-source tools!

<div align="center">

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor%20on-GitHub-%23EA4AAA?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/FaserF)&nbsp;&nbsp;
[![PayPal](https://img.shields.io/badge/Donate%20via-PayPal-%2300457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/FaserF)

</div>

## 📦 Installation

### HACS (Recommended)

This integration is fully compatible with [HACS](https://hacs.xyz/).

1. Open HACS in Home Assistant.
2. Click on the three dots in the top right corner and select **Custom repositories**.
3. Add `FaserF/ha-edeka` with category **Integration**.
4. Search for "EDEKA Offers".
5. Install and restart Home Assistant.

[![Open HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=FaserF&repository=ha-edeka&category=integration)

### Manual Installation

1. Download the latest release zip file.
2. Extract the `custom_components/edeka` folder into your Home Assistant's `custom_components` directory.
3. Restart Home Assistant.

## ⚙️ Configuration

1. Navigate to **Settings › Devices & Services** in Home Assistant.
2. Click **Add Integration** and search for **EDEKA Offers**.

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=edeka)

3. Enter your ZIP code, city name, or a direct **Market ID** to search for your local EDEKA market.
4. Select your specific market from the dropdown list.
5. Submit to create the device and entities.

> [!TIP]
> **How to find your Market ID manually (e.g. if automatic search is rate-limited):**
> 1. Go to [edeka.de/marktsuche.jsp](https://www.edeka.de/marktsuche.jsp) and search for your local store.
> 2. Click on your store to view its market page.
> 3. The **Market ID** can be found in the URL (e.g., `https://www.edeka.de/eh/nord/e-center-8001860/...` -> Market ID is `8001860`) or in the store details.
> 4. Enter this numeric ID directly into the integration setup to bypass the market search!

## 🔐 EDEKA / PAYBACK Login *(optional)*

Connecting your EDEKA account currently enables **one** additional feature:

- **📸 EDEKA / PAYBACK Loyalty Card QR Code**: Displays a live, scannable QR Code entity on your Home Assistant dashboard for scanning at the store checkout.

> [!WARNING]
> **Current Limitations — eBons & Coupons**
>
> EDEKA's personal data endpoints are protected by native-app authentication:
>
> - **eBons (receipts)** and **Coupons** require a proprietary, user-specific OAuth2 access token issued only by the official EDEKA iOS/Android App via Keycloak — it is **not** the `KEYCLOAK_IDENTITY` web session cookie.
> - The `KEYCLOAK_IDENTITY` cookie authenticates a *web browser session*, not a native app user session with the required `cheers-app.edeka.de` scope.
> - Until a compatible token exchange endpoint is discovered, the `Activated Coupons`, `Available Coupons`, and `Last Receipt` sensors will always show `0 items` / `Keine Kassenbons`.

Without account credentials, the integration operates in public mode and fetches weekly offers and market status.

---

### Option 1: PAYBACK / EDEKA Barcode Only *(simplest — 10 seconds)*

If you only want the **Checkout QR Code**:
1. Open the official **EDEKA App** or **PAYBACK App**, or check your physical **PAYBACK / EDEKA Card**.
2. Copy the **barcode number** (printed under the barcode or in the app).
3. In Home Assistant, go to **Settings > Devices & Services > EDEKA Offers > Options**.
4. Select **Configure EDEKA / PAYBACK Account**.
5. Paste your card barcode number into **EDEKA / PAYBACK Card Barcode Number**.
6. Submit. A new **Loyalty Card QR Code (`image`)** entity appears under the **EDEKA Account (DE)** device.

---

### Option 2: Session Token *(currently no additional benefit)*

A Session Token field exists in the integration for future use. At this time it does **not** unlock eBons or Coupons (see limitation above). You can skip this step.

<details>
<summary>How to extract the <code>KEYCLOAK_IDENTITY</code> cookie anyway (for future use / debugging)</summary>

1. Open [https://login.edeka/app](https://login.edeka/app) in your browser and log in.
2. Press **F12** → **Application** tab (Chrome/Edge) or **Storage** tab (Firefox).
3. Under **Cookies** → `https://login.edeka`, find **`KEYCLOAK_IDENTITY`**.
4. Copy its full value (`eyJ...`) and paste it as Session Token in Home Assistant.

</details>

---

## 🛠️ Options Flow & Account Features

You can easily configure or update the integration at any time:

1. Go to **Settings > Devices & Services > EDEKA Offers**.
2. Click **Configure** (Options).
3. Choose an action:
   - **⚙️ Save settings**: Update update interval (1–24 hours).
   - **💳 Configure EDEKA / PAYBACK Account**: Add or update your Loyalty Card number, Session Token, or Auto-Activation preference.
   - **🚪 Log out / Remove Account Data**: Clears account credentials and removes the Account Device.

## 🃏 Lovelace Cards

The community has built dedicated cards to display Edeka discounts beautifully in your dashboard.

### Custom Discounts Card
A dedicated Lovelace card maintained by the community:

[![Discounts Card](https://img.shields.io/badge/Lovelace-%20Discounts%20Card-brightgreen?style=for-the-badge&logo=home-assistant)](https://github.com/schblondie/discounts-card)

---
## 🧑‍💻 Development

### Ruff Linter
Ensure formatting and import order matches:
```bash
ruff check . --fix
```

### Type Checking
Ensure all files pass strict type checking:
```bash
mypy .
```

### Testing
Run the automated test suite:
```bash
pytest
```

## 💖 Credits & Acknowledgements

This integration relies on reverse-engineering work and community research from the following projects:

- **[ByteSizedMarius/edekarse-engineering](https://github.com/ByteSizedMarius/edekarse-engineering)**: For mapping out the EDEKA mobile API and providing Go/Python wrappers.
- **[foo-git/edeka-discounts](https://github.com/foo-git/edeka-discounts)**: For endpoint structures and headers.
- **[torbenpfohl/edeka-discounts](https://github.com/torbenpfohl/edeka-discounts)**: For API research and documentation.

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
