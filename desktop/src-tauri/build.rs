fn main() {
    // the commands behind window.FlowApp, each with its own permission (allow-notify-sync …) so that
    // capabilities/site.json can grant exactly these to the site's pages and nothing else
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "media_update",
            "notify_permission",
            "notify_ask",
            "notify_due",
            "notify_sync",
            "smoke_report",
        ]),
    ))
    .expect("tauri build script");
}
