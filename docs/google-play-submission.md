# Google Play Submission Pack

## Release Artifact

- Android App Bundle for Google Play:
  - `bodaboda_android/app/build/outputs/bundle/release/app-release.aab`
- APK for direct installation and testing:
  - `bodaboda_android/app/build/outputs/apk/release/app-release.apk`

## Current App Identity

- App name: `BODA AU`
- Package name: `com.bodaboda.app`
- Version code: `3`
- Version name: `1.2`

## Store Listing Draft

### App Name

`BODA AU`

### Short Description

`Book bodaboda and bajaji rides across Zanzibar in English or Swahili.`

### Full Description

`BODA AU helps passengers and drivers connect for everyday transport across Zanzibar.

Passengers can request rides between known Zanzibar pickup and dropoff points, view fare estimates, track ride progress, manage safety contacts, and switch between English and Swahili.

Drivers can create a profile, submit verification details, go online when available, receive ride requests, update live status, and manage completed trips from one dashboard.

Key features:
- Request bodaboda and bajaji rides across Zanzibar
- Choose English or Swahili
- View fare and ride details before sending a request
- Save emergency contacts for safety support
- Receive ride and service notifications
- Driver verification and online availability controls
- Ride history and account support tools

BODA AU is designed to make local transport coordination simpler, faster, and safer for riders and drivers in Zanzibar.`

### Support Contact

- Support email: `support@zanzibarbodaboda.tz`
- Support phone: `+255 787 104 836`
- Privacy policy URL once live:
  - `https://<your-domain>/terms-privacy/`

## Play Console Checklist

1. Create the app in Play Console.
2. Use default language `English (United States)`.
3. Set app type to `App`.
4. Choose `Free` or `Paid` based on your business plan.
5. Accept Play App Signing.
6. Upload `app-release.aab` to Internal testing first.
7. Fill in the main store listing with the text above.
8. Add support email, phone, and website if available.
9. Add the privacy policy URL using the public `terms-privacy` page.
10. Complete App content declarations.
11. Complete Data safety based on the actual released behavior.
12. After internal testing passes, promote to Production.

## Privacy Policy Review Notes

The privacy policy page was expanded to cover:

- operator identity
- account data collected
- location usage
- emergency contact data
- driver verification data
- notifications
- data sharing rules
- retention and security
- correction, closure, and deletion requests
- support contact details

Before submission, make sure the public site domain is live and the privacy page is reachable without login.

## Data Safety Notes

Based on the current codebase, you should carefully review these categories in Play Console before submitting:

- Personal info:
  - name
  - phone number
- Photos and files:
  - profile images
  - driver verification documents
- Location:
  - approximate and precise location when permission is granted
- App activity:
  - ride requests, ride history, ratings, support activity
- Contacts entered by the user:
  - emergency contact names and phone numbers

These notes are a code-based draft, not a legal declaration. Confirm the final answers against the exact production behavior before publishing.

## Graphic Assets Checklist

Required for Play listing:

- App icon:
  - PNG
  - `512 x 512`
- Feature graphic:
  - PNG or JPG
  - `1024 x 500`
- Screenshots:
  - at least `2`
  - recommended `4+`
  - portrait `1080 x 1920` or better for phone screenshots

Recommended screenshot set:

1. Language selection popup
2. Passenger home or request form
3. Driver dashboard
4. Ride history or safety features
5. Profile and language settings

Optional localized assets:

- English screenshots
- Swahili screenshots

## Important Submission Notes

- Google Play expects the `.aab` for a new app.
- The privacy policy must be on a public non-PDF URL.
- If your Play developer account is a personal account created after November 13, 2023, Google may require testing milestones before production release.
