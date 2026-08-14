# Project-local Android tooling

`aapt.exe` is a project-local fallback for Android APK metadata parsing. Runtime resolution still allows `ANDROID_UI_AAPT_PATH` to override this file.

Current binary record:

- file: `aapt.exe`
- version: `Android Asset Packaging Tool, v0.2-5016651`
- SHA-256: `29FF3F525786F8014DED9F5A093007DC8E986F5F3D29C345F2FDE93416C400EB`
- local source at import time: `D:\work\SDKUI\plugins\aapt.exe`
- signature status at import time: not signed

Keep the binary only when its provenance and redistribution terms are acceptable for the project. Replace it only with a trusted Android SDK Build-Tools `aapt.exe`, update this record, and verify `aapt.exe version` before committing the change.
