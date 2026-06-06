# Xcode Archive Investigation

1. Root cause:
   The app and extension targets are present and valid, but the project had no committed shared scheme file at `ios/voiceMixer.xcodeproj/xcshareddata/xcschemes/`. Xcode can synthesize schemes for `xcodebuild`, but the Xcode UI can still show an empty Scheme menu/Product menu if no user/shared scheme state exists. Committing a shared host-app scheme is the reliable fix.

2. `xcodebuild -list -project ios/voiceMixer.xcodeproj` result:
   Xcode printed sandbox/local simulator and DerivedData warnings, then the project listing:

   ```text
   Information about project "voiceMixer":
       Targets:
           voiceMixer
           voiceMixerMessages

       Build Configurations:
           Debug
           Release

       If no build configuration is specified and -scheme is not passed then "Debug" is used.

       Schemes:
           voiceMixer
           voiceMixerMessages
   ```

3. On-disk scheme inspection:
   Before the fix, `ios/voiceMixer.xcodeproj/xcshareddata/` existed but `ios/voiceMixer.xcodeproj/xcshareddata/xcschemes/` did not. There were zero committed `.xcscheme` files.

4. Target sanity check:
   `ios/voiceMixer.xcodeproj/project.pbxproj` contains both native targets:
   - `voiceMixer`, product type `com.apple.product-type.application`, product `voiceMixer.app`.
   - `voiceMixerMessages`, product type `com.apple.product-type.app-extension.messages`, product `voiceMixerMessages.appex`.
   The host app target depends on `voiceMixerMessages` and has an `Embed Foundation Extensions` build phase containing `voiceMixerMessages.appex`, so the app target is the correct archive target.

5. Fix applied:
   I created the shared host app scheme:

   ```text
   ios/voiceMixer.xcodeproj/xcshareddata/xcschemes/voiceMixer.xcscheme
   ```

   It references the host app target `voiceMixer` (`BlueprintIdentifier = 1A36464BAE0280C2C9635BCA`) and archives with the `Release` configuration. The extension is picked up through the existing target dependency/embed phase.

6. Validation:
   - `xmllint --noout ios/voiceMixer.xcodeproj/xcshareddata/xcschemes/voiceMixer.xcscheme` passed.
   - `xcodebuild -project ios/voiceMixer.xcodeproj -scheme voiceMixer -showBuildSettings -configuration Release -destination 'generic/platform=iOS' -derivedDataPath /tmp/voiceMix-dd` passed and resolved `PRODUCT_TYPE = com.apple.product-type.application`, `PRODUCT_BUNDLE_IDENTIFIER = com.aaron.voiceMixer`, `ARCHS = arm64`, and `PLATFORM_NAME = iphoneos`.

7. Archive steps in Xcode:
   1. Close and reopen `ios/voiceMixer.xcodeproj`.
   2. Select the `voiceMixer` scheme.
   3. Select destination `Any iOS Device (arm64)`.
   4. Open `Product > Archive`.
   5. In Organizer, select the archive, then `Distribute App` for TestFlight upload.

8. Signing prerequisite:
   `DEVELOPMENT_TEAM` is currently empty for both targets in `project.pbxproj`, and both targets are set to automatic signing. Before distributing, set a team for both `voiceMixer` and `voiceMixerMessages`:
   `Project navigator > voiceMixer project > Targets > voiceMixer > Signing & Capabilities > Team`, then repeat for `voiceMixerMessages`.

   The two bundle IDs also need to exist in the Apple Developer account or be creatable by automatic signing:
   - `com.aaron.voiceMixer`
   - `com.aaron.voiceMixer.Messages`
