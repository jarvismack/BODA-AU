# BODA AU Android WebView App

## 1) Update the live URL
Edit:
`app/src/main/res/values/strings.xml`

Set:
```
<string name="base_url">https://your-domain-or-ngrok-url</string>
```

## 2) Build debug APK (for testing)
```
./gradlew assembleDebug
```
APK output:
`app/build/outputs/apk/debug/app-debug.apk`

## 3) Create a release keystore
```
keytool -genkeypair -v \
  -keystore keystore/bodaboda-release.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias bodaboda
```

## 4) Create keystore.properties
Copy template:
```
cp keystore.properties.example keystore.properties
```
Fill values with your real passwords.

## 5) Build release AAB
```
./gradlew bundleRelease
```
AAB output:
`app/build/outputs/bundle/release/app-release.aab`

## 6) Upload to Play Console
- Create Play Developer account
- Upload the AAB
- Provide screenshots, icon, privacy policy

## Notes
- This app uses WebView to load your live BODA AU web app.
- Offline screen shows when the device has no internet.
