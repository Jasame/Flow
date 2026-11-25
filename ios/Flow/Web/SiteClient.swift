import Foundation
import WebKit

enum SiteError: Error, Equatable {
    case status(Int, code: String, message: String)  // the HTTP status, the answer's `code` and `error`
    case shape
    case signedOut
}

/// The site's API from the native side (the server voice for a whole text read with the screen locked, the counts for
/// reminders), signed in with the web view's own cookies; a cookie the server renews goes back into the web view.
@MainActor
final class SiteClient {
    let base: URL
    var cookieStore: WKHTTPCookieStore?
    /// the saved session put back into WebKit at launch (Shell): requests wait for it, or they would go out signed out
    var ready: Task<Void, Never>?
    private let session: URLSession
    private var csrfToken: String?

    init(base: URL) {
        self.base = base
        let c = URLSessionConfiguration.default
        c.httpShouldSetCookies = false
        c.httpCookieAcceptPolicy = .never
        c.httpCookieStorage = nil
        c.urlCache = nil
        c.timeoutIntervalForRequest = 25
        c.httpAdditionalHeaders = ["User-Agent": "Yuliu/\(AppConfig.version) \(AppConfig.userAgentSuffix)"]
        session = URLSession(configuration: c)
    }

    func url(_ path: String) -> URL? { URL(string: path, relativeTo: base)?.absoluteURL }

    /// The web view's cookies that go with a request to url (RFC 6265 domain and path matching).
    func cookies(for url: URL) async -> [HTTPCookie] {
        await ready?.value
        guard let store = cookieStore, let host = url.host?.lowercased() else { return [] }
        let path = url.path.isEmpty ? "/" : url.path
        return await store.allCookies().filter { c in
            let d = c.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
            let domainOK = host == d || host.hasSuffix("." + d)
            let pathOK = path.hasPrefix(c.path.isEmpty ? "/" : c.path)
            let notExpired = c.expiresDate.map { $0 > Date() } ?? true
            return domainOK && pathOK && notExpired && (!c.isSecure || url.scheme == "https")
        }
    }

    /// GET (body nil) or POST JSON; with csrf, the session's token as the page sends it (X-CSRF-Token).
    func send(_ path: String, body: [String: Any]? = nil, csrf: String? = nil, timeout: TimeInterval = 25) async throws -> (Data, HTTPURLResponse) {
        guard let url = url(path) else { throw SiteError.shape }
        var req = URLRequest(url: url, timeoutInterval: timeout)
        let cs = await cookies(for: url)
        for (k, v) in HTTPCookie.requestHeaderFields(with: cs) { req.setValue(v, forHTTPHeaderField: k) }
        if let body {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
            var token = csrf
            if token == nil { token = await self.csrf() }
            if let token { req.setValue(token, forHTTPHeaderField: "X-CSRF-Token") }
        }
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw SiteError.shape }
        await keepCookies(http, url: url)
        return (data, http)
    }

    /// A JSON object; a non-2xx answer throws its `error` text (status 401: signed out).
    func json(_ path: String, body: [String: Any]? = nil, csrf: String? = nil, timeout: TimeInterval = 25) async throws -> [String: Any] {
        let (data, http) = try await send(path, body: body, csrf: csrf, timeout: timeout)
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if http.statusCode == 401 { throw SiteError.signedOut }
        guard (200..<300).contains(http.statusCode) else {
            throw SiteError.status(http.statusCode, code: (obj?["code"] as? String) ?? "", message: (obj?["error"] as? String) ?? "")
        }
        guard let obj else { throw SiteError.shape }
        return obj
    }

    /// The signed-in session's CSRF token (/api/session → user.csrf), asked once.
    func csrf() async -> String? {
        if let csrfToken { return csrfToken }
        guard let j = try? await json("/api/session"), let u = j["user"] as? [String: Any], let t = u["csrf"] as? String else { return nil }
        csrfToken = t
        return t
    }

    /// The session changed in the web view (signed in, out, as someone else): the next POST asks for its token again.
    func forgetSession() { csrfToken = nil }

    private func keepCookies(_ http: HTTPURLResponse, url: URL) async {
        var fields: [String: String] = [:]
        for (k, v) in http.allHeaderFields { if let k = k as? String, let v = v as? String { fields[k] = v } }
        guard fields.keys.contains(where: { $0.caseInsensitiveCompare("Set-Cookie") == .orderedSame }), let store = cookieStore else { return }
        for c in HTTPCookie.cookies(withResponseHeaderFields: fields, for: url) { await store.setCookie(c) }
        csrfToken = nil
    }
}
