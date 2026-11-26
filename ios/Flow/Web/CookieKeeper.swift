import Foundation
import Security
import WebKit

/// Keeps the learner signed in. The site's session is a cookie (flow_session, HttpOnly, 30 days, renewed while used),
/// and the other accounts this device remembers for 「切换账号」 are another (flow_more, HttpOnly, B6); WebKit stores
/// them on disk on its own schedule, so an app closed right after signing in or switching could lose them. A copy of
/// each goes to the Keychain (this device only, not in backups) whenever it changes, and comes back at launch when
/// WebKit has none; one the site cleared (signed out, an account removed) is deleted from the Keychain too.
/// Keychain items outlive deleting the app (WebKit's data does not): the first launch of an install wipes the copy, so a
/// reinstall on a shared iPad never opens someone else's account.
@MainActor
final class CookieKeeper: NSObject, WKHTTPCookieStoreObserver {
    nonisolated static let name = "flow_session"
    /// the cookies kept: the session, then the other remembered accounts
    nonisolated static let names = [name, "flow_more"]
    private let service = "cn.flowlang.app.session"
    private let installed = "flow.installed"
    private weak var store: WKHTTPCookieStore?
    private var last: String?
    /// the session changed (signed in, out, as someone else): the native side forgets what it knew about it
    var changed: (() -> Void)?

    /// Before the first page loads: put the saved session back if WebKit lost it, then watch for changes.
    func start(_ store: WKHTTPCookieStore, host: String) async {
        self.store = store
        if !UserDefaults.standard.bool(forKey: installed) {  // a new install (UserDefaults go with the app, the Keychain does not)
            SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service] as CFDictionary)
            UserDefaults.standard.set(true, forKey: installed)
        }
        let all = await store.allCookies()
        for name in Self.names where !all.contains(where: { $0.name == name && Self.matches($0, host) }) {
            if let saved = load(host, name), let c = HTTPCookie(properties: saved), (c.expiresDate ?? .distantPast) > Date() {
                await store.setCookie(c)
            }
        }
        store.add(self)
    }

    nonisolated func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
        Task { @MainActor in await self.save() }
    }

    private func save() async {
        guard let store, let host = AppConfig.origin.host?.lowercased() else { return }
        let all = await store.allCookies()
        for name in Self.names {
            let c = all.first { $0.name == name && Self.matches($0, host) }
            if name == Self.name, c?.value != last {
                last = c?.value
                changed?()
            }
            if let c, !c.value.isEmpty, (c.expiresDate ?? .distantPast) > Date() {
                var p: [String: Any] = [:]
                for (k, v) in c.properties ?? [:] { p[k.rawValue] = v }
                if let d = try? PropertyListSerialization.data(fromPropertyList: p, format: .binary, options: 0) { write(host, name, d) }
            } else {
                delete(host, name)  // signed out, the accounts removed (the server cleared it) or expired
            }
        }
    }

    static func matches(_ c: HTTPCookie, _ host: String) -> Bool {
        let d = c.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        return host == d || host.hasSuffix("." + d)
    }

    // ---- Keychain: one generic-password item per site host and cookie (the session's keeps its old name: the host)
    nonisolated static func account(_ host: String, _ name: String) -> String { name == Self.name ? host : host + "/" + name }

    private func query(_ host: String, _ name: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: Self.account(host, name)]
    }

    private func load(_ host: String, _ name: String) -> [HTTPCookiePropertyKey: Any]? {
        var q = query(host, name)
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data,
              let p = try? PropertyListSerialization.propertyList(from: d, format: nil) as? [String: Any] else { return nil }
        var props: [HTTPCookiePropertyKey: Any] = [:]
        for (k, v) in p { props[HTTPCookiePropertyKey(k)] = v }
        return props
    }

    private func write(_ host: String, _ name: String, _ data: Data) {
        let q = query(host, name)
        let attrs: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        if SecItemUpdate(q as CFDictionary, attrs as CFDictionary) == errSecItemNotFound {
            var add = q
            add.merge(attrs) { a, _ in a }
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    private func delete(_ host: String, _ name: String) { SecItemDelete(query(host, name) as CFDictionary) }
}
