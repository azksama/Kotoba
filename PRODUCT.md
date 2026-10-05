# Kotoba
<!-- impeccable:product-schema 1 -->

## Platform
android

## Stack
Rust + Tauri 2, requested by the user. React/TypeScript frontend and Rust HTTPS companion on Windows chosen under the user's instruction to handle all decisions. Existing Python translator remains the validated translation engine.

## Users
The owner of a Windows RTX 4070 SUPER computer translating Japanese game JSON into English, launching and monitoring work from an Android phone.

## Product Purpose
Import a JSON, inspect selected text, start the local GPU translation remotely, follow durable progress, and save the translated JSON back to the phone.

## Operating Context
The PC must remain on and reachable. LAN connectivity is available; external network routing is to be established or documented honestly. Jobs continue on the PC when the phone app closes.

## Capabilities and Constraints
Preserve the existing translator and original files. Provide job history, cancellation, retry, reports, a glossary, source-field filters and clear offline/error states. Secure HTTPS pairing and Android Keystore. Native document pick/save. Android testing uses only Android SDK ADB, instrumentation, Logcat and Android Studio Emulator; ARTEMIS is prohibited.

## Evidence on Hand
Existing translator: 23 passing tests, real TranslateGemma 12B translation and 100 percent GPU loading previously verified. No physical phone or external-network test has yet occurred.

## Product Principles
Data integrity before throughput. Visible progress with no dependence on foreground phone execution. Secrets stay local. State clearly when a translation needs linguistic review.

## Decisions
User delegated remaining design and setup choices. Name Kotoba, three views Translate/History/Connection, French UI, direct implementation. These are implementation decisions rather than claims of pre-existing brand.
