# Safari Geni token extractor: draft, device-unverified

This is JavaScript for a manually built Safari Share Sheet Shortcut, not an installable Shortcut download. It does not authorize Geni or validate token ownership. The complete flow has not been verified on an iPhone. Do not use a real token until code review and the synthetic device test below pass.

Never put an app secret or real token in a repository, issue, PR, screenshot, chat or email. Choose and verify the secure destination field before authorization. Never paste into Safari's search/address bar.

## Manual action chain

Paste the contents of extract-token.js without Markdown fences. A chip means the named Shortcuts variable, not text typed into an action.

1. Create a Shortcut named Geni token. Enable Show in Share Sheet and accept only Safari webpages. Run it only from Safari Share Sheet, never from the editor, Siri, widget or another Shortcut.
2. Add Current Date, then Adjust Date: add 2 minutes to Current Date. This computes expiry afresh on every run. The clipboard expires after two minutes; paste within that time. A late paste yields no token and can look like failure.
3. Add Text containing the fixed non-secret marker GENI_TOKEN_NOT_READY. Add Copy to Clipboard, explicitly using this Text result, with Local Only enabled and Expire At explicitly set to the Adjusted Date chip. This replaces any older clipboard secret before extraction.
4. Add Run JavaScript on Webpage. Its input must be the original Shortcut Input chip, not the preceding Text/clipboard/date result. Replace its sample script with extract-token.js.
5. Add Copy to Clipboard explicitly using the JavaScript Result chip. Enable Local Only; set Expire At to the Adjusted Date chip. Add a final Nothing action so the token is not returned as Share Sheet output. Do not use Stop and Output with the token.
6. If needed, enable Allow Running Scripts in Shortcuts' Advanced settings. Permit execution only after checking the Geni page and this Shortcut. Permission may persist per Shortcut/page; no one-time permission is promised.

Do not add Show Result, Quick Look, notification, speech, file, network, mail or messaging actions. Local Only prevents Handoff clipboard sharing, not local clipboard readers. On ANY error, do not paste anything. After secure paste, copy a harmless word and close the tab.

## Required synthetic on-device check, before real authorization

A separate synthetic harness must use the exact same extraction logic with an explicitly separate fake-page origin/path, never weaken the production Geni origin guard. A separate synthetic harness is proposed in PR152. Do not assume it is deployed until its canonical page has been checked. Use its TEST extractor, which may differ from this production file only in the exact host/path guards. The synthetic value must start ZZ and not be a real token. The harness is not a Geni endpoint or evidence of vendor behavior.

- Verify the action chips and that this iOS version exposes Local Only and Expire At. Stop if either option is absent. Check the dynamic date chips with a token-free screenshot before testing.
- Invoke through Safari Share Sheet only. Confirm the fake fragment clears, the exact synthetic token reaches a harmless local test field, nothing is displayed or returned to Safari, and clipboard expiry works after two minutes.
- Test a rejected page/error: only the fixed marker should remain, and no older token may be pasted.
- Clear the clipboard with a harmless word and close the test tab. Restore/check the exact production origin/path script before any real authorization.

This device check is NOT complete. A working desktop-browser JavaScript test does not establish iPhone Share Sheet or clipboard behavior.

## After all checks pass

Use only an app key you have independently checked in your own application settings. Geni's desktop documentation specifies `https://www.geni.com/platform/oauth/authorize` with `client_id=<your-app-key>`, `response_type=token` and `display=desktop`. This is a parameter description, not a prepared link for a particular app. Do not change registered callbacks based on this document. Stop if the actual return is not the exact Geni success URL this script accepts.

Choose a password-manager/secure-vault secret field before starting, not Notes, email, chat or a browser address/search field. Do not use any destination supplied by a success page or an unsolicited message.

Run only on a success page reached seconds earlier from authorization you personally started in the SAME tab. Never run on a success URL from a message, email, QR code, bookmark or reopened history entry. The extractor does not bind `state` to a locally started transaction: an attacker-supplied token can pass syntax checks. Storage is not proof of ownership. Before any account write, a separate owner-identity check must resolve the token's authoritative self-profile and compare it to the intended owner; stop if this cannot be verified. The [parent-creation design](../../docs/profile-creation-design.md) and `exact_owner_identity` in [human-parent-release-gates.json](../../docs/human-parent-release-gates.json) list this as a release blocker, not an implemented safety guarantee.

Shortcuts' isolated-versus-page JavaScript content world is not verified here. If page scripts can redefine URL parsing or history primitives, this guard is not a defense against a hostile page. The synthetic harness does not settle that assumption or prove Geni-page behavior.

Follow your application's documented authorization instructions. On the returned Geni success page, never copy/share its address or screenshot it. Run the Shortcut from Safari Share Sheet. On error stop; report only the fixed error, not URL/content. Paste only into the secure field chosen beforehand, then copy a harmless word and close the tab.

The extractor permits only the exact HTTPS Geni success URL with no query delimiter, strict fragment decoding, unique allowed keys and a supported token-character subset. That subset is a fail-closed filter, not a proven Geni format. It clears the URL before completing with the token; clearing failure returns no token. Fragment data is not sent in the HTTP request/referrer, but remains readable by the Geni page's scripts and may enter browser history. Clearing cannot erase prior reads or history.

## Offline tests

Run `node test-extract.js`. Tests use only synthetic ZZ values and include parsing failures, URL boundaries, length limits, encoded values, clear failures and completion order. The forbidden-primitives check is a source-level smoke check, not a full security proof.

## Sources and terms

Geni documents an internal success redirect for its desktop flow: https://www.geni.com/platform/developer/help/oauth_desktop . The exact fragment route assumed here is reported by an independent implementation: https://github.com/dmalch/go-geni/releases/tag/v1.28.0 . It remains unverified for an actual iPhone session. Fragment HTTP behavior: https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Fragment . Apple action setup and clipboard options: https://support.apple.com/guide/shortcuts/use-the-run-javascript-on-webpage-action-apdb71a01d93/ios and https://support.apple.com/guide/shortcuts/about-actions-in-complicated-shortcuts-apd081d9d61f/ios .

This project is not affiliated with or endorsed by Geni or Apple. Shortcuts is an Apple product. Supplied under the repository MIT license, AS IS, without warranty.

## Mac preparation

Apple also supports Run JavaScript on Active Safari Tab on macOS. Configure Services Menu, Safari webpages only, and invoke through Safari > Services. Use the same fixed-marker reset, dynamic expiry, explicit result wiring and final Nothing. Confirm this Mac exposes Local Only and Expire At; stop if absent. Do not use a real token before a synthetic Mac test. Source: https://support.apple.com/guide/shortcuts-mac/use-the-run-javascript-on-webpage-action-apdb71a01d93/mac .
