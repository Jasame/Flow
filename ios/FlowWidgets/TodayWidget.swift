import SwiftUI
import WidgetKit

/// 「今天」 on the home screen and the lock screen: the words to review today (tap: 复习), and on the wider one 今日好句
/// (tap: 今日). The numbers are the app's (TodayCard, written when it last asked the site); the widget only shows them.
struct TodayWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "today", provider: TodayProvider()) { entry in
            TodayView(entry: entry)
                .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("今天")
        .description("今天要复习的词和今日好句，点一下就去复习。")
        .supportedFamilies([.systemSmall, .systemMedium, .accessoryCircular, .accessoryRectangular, .accessoryInline])
    }
}

struct TodayEntry: TimelineEntry {
    let date: Date
    let card: TodayCard?
}

struct TodayProvider: TimelineProvider {
    func placeholder(in context: Context) -> TodayEntry { TodayEntry(date: Date(), card: .sample) }

    func getSnapshot(in context: Context, completion: @escaping (TodayEntry) -> Void) {
        // the widget gallery shows an example until the app has written today's numbers
        completion(TodayEntry(date: Date(), card: context.isPreview ? (SharedStore.load() ?? .sample) : SharedStore.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<TodayEntry>) -> Void) {
        let now = Date(), card = SharedStore.load()
        // past midnight (China time) the same numbers are yesterday's: a second entry then says to open the app
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Asia/Shanghai") ?? .current
        let midnight = cal.startOfDay(for: now).addingTimeInterval(86_400 + 60)
        completion(Timeline(entries: [TodayEntry(date: now, card: card), TodayEntry(date: midnight, card: card)], policy: .after(midnight)))
    }
}

/// The brand colours, as the app has them (Accent): 松绿 or 靛蓝, lighter in the dark
private func accent(_ name: String?) -> Color {
    name == "indigo"
        ? Color(light: (0x34, 0x61, 0xD1), dark: (0x8E, 0xAE, 0xFC))
        : Color(light: (0x1F, 0x9D, 0x55), dark: (0x3C, 0xCF, 0x7C))
}

private extension Color {
    init(light: (Int, Int, Int), dark: (Int, Int, Int)) {
        self = Color(uiColor: UIColor { t in
            let c = t.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: CGFloat(c.0) / 255, green: CGFloat(c.1) / 255, blue: CGFloat(c.2) / 255, alpha: 1)
        })
    }
}

struct TodayView: View {
    let entry: TodayEntry
    @Environment(\.widgetFamily) private var family

    private var card: TodayCard? { entry.card }
    private var review: URL { SharedStore.link("#/review") }
    private var today: URL { SharedStore.link("#/") }
    private var stale: Bool { card?.stale(now: entry.date) ?? false }

    /// what the numbers cannot say: nothing written yet, nobody signed in, not agreed yet, or yesterday's
    private var notice: String? {
        guard let card else { return "打开语流 App，这里就显示今天要复习的词" }
        switch card.state {
        case .signedOut: return "登录语流以后，这里显示今天要复习的词"
        case .paused: return "先在语流里同意用户协议和隐私说明"
        case .ok: return stale ? "打开语流看看今天的" : nil
        }
    }

    var body: some View {
        switch family {
        case .accessoryInline: inline
        case .accessoryCircular: circular
        case .accessoryRectangular: rectangular
        case .systemMedium: medium
        default: small.widgetURL(review)
        }
    }

    // MARK: home screen

    private var small: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("今天").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            Spacer(minLength: 4)
            if let notice, card?.state != .ok || card == nil {
                Text(notice).font(.footnote).foregroundStyle(.secondary)
            } else if let card, card.due + card.new == 0 {
                Text("今天的词").font(.footnote).foregroundStyle(.secondary)
                Text("都复习完了").font(.title3.weight(.semibold))
            } else if let card {
                Text("\(card.due)").font(.system(size: 42, weight: .semibold, design: .rounded)).foregroundStyle(accent(card.accent))
                    .minimumScaleFactor(0.6).lineLimit(1)
                Text("个词要复习").font(.footnote)
                Text(card.new > 0 ? "新词 \(card.new)" + (card.minutes > 0 ? " · 约 \(card.minutes) 分钟" : "") : (card.minutes > 0 ? "约 \(card.minutes) 分钟" : " "))
                    .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                if stale { Text("打开语流看看今天的").font(.caption2).foregroundStyle(.secondary).lineLimit(1) }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
    }

    private var medium: some View {
        HStack(alignment: .top, spacing: 14) {
            Link(destination: review) { small }
            Divider()
            Link(destination: today) { lineOrRead }
        }
    }

    /// 今日好句 with its label and source as the site shows them; without one, 今天这篇
    @ViewBuilder private var lineOrRead: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let line = card?.line {
                Text("今日好句 · \(line.label)").font(.caption.weight(.semibold)).foregroundStyle(.secondary).lineLimit(1)
                Text(line.en).font(.subheadline).lineLimit(3).minimumScaleFactor(0.85)
                Text(line.zh).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                if !line.source.isEmpty { Text(line.source).font(.caption2).foregroundStyle(.tertiary).lineLimit(1) }
            } else if let read = card?.read {
                Text("今天这篇").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Text(read.title).font(.subheadline).lineLimit(3)
            } else {
                Text("今日好句").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Text("打开语流就有").font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    // MARK: lock screen

    private var inline: some View {
        Group {
            if let card, card.state == .ok, !stale { Text(card.due > 0 ? "语流 · 复习 \(card.due) 个词" : "语流 · 今天的词复习完了") } else { Text("语流") }
        }
        .widgetURL(review)
    }

    private var circular: some View {
        ZStack {
            AccessoryWidgetBackground()
            VStack(spacing: 0) {
                if let card, card.state == .ok, !stale {
                    Text("\(card.due)").font(.title3.weight(.semibold)).minimumScaleFactor(0.5).lineLimit(1)
                    Text("复习").font(.caption2)
                } else {
                    Image(systemName: "rectangle.stack").font(.title3)
                }
            }
        }
        .widgetURL(review)
    }

    private var rectangular: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("语流").font(.headline)
            if let card, card.state == .ok, !stale {
                Text(card.due > 0 ? "复习 \(card.due) 个词" : "今天的词复习完了").lineLimit(1)
                if card.new > 0 || card.minutes > 0 {
                    Text([card.new > 0 ? "新词 \(card.new)" : nil, card.minutes > 0 ? "约 \(card.minutes) 分钟" : nil].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).lineLimit(1)
                }
            } else {
                Text(notice ?? "").font(.caption).lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .widgetURL(review)
    }
}

#Preview(as: .systemMedium) {
    TodayWidget()
} timeline: {
    TodayEntry(date: Date(), card: .sample)
}
