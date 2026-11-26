import CoreSpotlight
import Foundation
import UniformTypeIdentifiers

/// 「在系统搜索里找生词」 (iOS 专属功能, item 7; default off): the learner's own word and phrase cards in the iPhone's
/// search, on this phone only (the system's local index, Core Spotlight; no search with a language model). The list is
/// the site's /api/next/cards/index (语流 B2, #366), asked when the app comes to the front with the version it has
/// (`?v=`: unchanged → nothing to do). A word found there opens the app on #/cards/find/<word>. Switched off, signed
/// out or not agreed to the storage: the index is emptied.
@MainActor
enum WordSearch {
    nonisolated static let domain = "cn.flowlang.app.cards"
    private static let versionKey = "flow.wordsearch.v"
    private static var busy = false

    /// The app came to the front, or the switch went on: the index follows the site's list.
    static func refresh(site: SiteClient) async {
        guard Features.on(.wordSearch) else { return }
        guard !busy, CSSearchableIndex.isIndexingAvailable() else { return }
        #if BETA
        if UserDefaults.standard.bool(forKey: "FlowWordSearchSample") {  // screenshots and tests: a few words, nobody's
            try? await CSSearchableIndex.default().indexSearchableItems(items(sample))
            return
        }
        #endif
        busy = true
        defer { busy = false }
        let had = UserDefaults.standard.string(forKey: versionKey)
        do {
            let j = try await site.json("/api/next/cards/index" + (had.map { "?v=" + $0 } ?? ""))
            guard Features.on(.wordSearch), let v = j["v"] as? String else { return }  // switched off meanwhile
            if (j["same"] as? Bool) == true, v == had { return }
            let items = Self.items((j["words"] as? [[String: Any]]) ?? [])
            try await CSSearchableIndex.default().deleteSearchableItems(withDomainIdentifiers: [domain])
            if !items.isEmpty { try await CSSearchableIndex.default().indexSearchableItems(items) }
            UserDefaults.standard.set(v, forKey: versionKey)
        } catch SiteError.signedOut {
            await clear()  // nobody's words on a phone nobody is signed in on
        } catch SiteError.status(403, _, _) {
            await clear()  // not agreed to the storage (or paused): no words of it in the phone's search
        } catch {
            // offline or the site busy: the index keeps what it had until the next time
        }
    }

    /// The switch went off: everything this app put in the phone's search goes.
    static func clear() async {
        UserDefaults.standard.removeObject(forKey: versionKey)
        try? await CSSearchableIndex.default().deleteSearchableItems(withDomainIdentifiers: [domain])
    }

    #if BETA
    nonisolated static var sample: [[String: Any]] { [["id": 1, "text": "make up for", "zh": "弥补"],
                                                     ["id": 2, "text": "deliberately", "zh": "从容地；故意地"],
                                                     ["id": 3, "text": "rainbow", "zh": "彩虹"]] }
    #endif

    /// One search entry per card: the word (or phrase) as the title, its first meaning under it.
    nonisolated static func items(_ words: [[String: Any]]) -> [CSSearchableItem] {
        words.prefix(5000).compactMap { w in
            guard let text = (w["text"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { return nil }
            let id = (w["id"] as? Int).map(String.init) ?? (w["id"] as? String) ?? text
            let a = CSSearchableItemAttributeSet(contentType: .text)
            a.title = text
            a.contentDescription = (w["zh"] as? String) ?? ""
            a.keywords = [text]
            let item = CSSearchableItem(uniqueIdentifier: identifier(id: id, text: text), domainIdentifier: domain, attributeSet: a)
            item.expirationDate = .distantFuture
            return item
        }
    }

    /// card/<id>/<text>: the text comes back when the learner picks it in the search (it may contain anything, even '/')
    nonisolated static func identifier(id: String, text: String) -> String { "card/\(id)/\(text)" }

    /// The page for a search entry the learner picked: #/cards/find/<word>, the word as encodeURIComponent writes it.
    nonisolated static func path(forIdentifier ident: String) -> String? {
        let parts = ident.split(separator: "/", maxSplits: 2, omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0] == "card", !parts[2].isEmpty else { return nil }
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!~*'()")
        guard let enc = String(parts[2].prefix(80)).addingPercentEncoding(withAllowedCharacters: allowed) else { return nil }
        return "#/cards/find/" + enc
    }
}
