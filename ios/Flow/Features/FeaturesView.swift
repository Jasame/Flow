import SwiftUI

/// 我的 → 设置 → 「iOS 专属功能」 (the page's row calls FlowApp.call('app.settings')): a switch for each feature this
/// iPhone has, grouped as on the plan (ios-27-features.md); what each switch does in one grey line under it.
struct FeaturesView: View {
    let accent: Color
    @Environment(\.dismiss) private var dismiss
    @AppStorage(Feature.offlinePacks.key) private var packsOn = Feature.offlinePacks.defaultOn

    var body: some View {
        NavigationStack {
            Form {
                ForEach(Feature.Group.allCases, id: \.self) { g in
                    let fs = Feature.allCases.filter { $0.group == g && $0.available }
                    if !fs.isEmpty {
                        Section(g.rawValue) {
                            ForEach(fs) { FeatureRow(feature: $0) }
                        }
                    }
                    if g == Feature.offlinePacks.group, packsOn { PacksSection() }  // right under its own switch
                }
                Section {
                } footer: {
                    Text("这些开关只存在这台手机上，不会上传。换手机或者删掉 App 以后，要重新设一次。")
                }
            }
            .navigationTitle("iOS 专属功能")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }.accessibilityIdentifier("features.done")
                }
            }
        }
        .tint(accent)
    }
}

private struct FeatureRow: View {
    let feature: Feature
    @AppStorage private var on: Bool

    init(feature: Feature) {
        self.feature = feature
        _on = AppStorage(wrappedValue: feature.defaultOn, feature.key)
    }

    var body: some View {
        Toggle(isOn: Binding(get: { on }, set: { Features.set(feature, $0) })) {
            VStack(alignment: .leading, spacing: 3) {
                Text(feature.title)
                Text(feature.detail).font(.footnote).foregroundStyle(.secondary)
            }
        }
        .accessibilityIdentifier("feature." + feature.rawValue)
    }
}

/// 离线朗读包, when it is on: what is kept, and fetching today's now
private struct PacksSection: View {
    @State private var packs = Packs.shared

    var body: some View {
        Section {
            let kept = packs.entries.values.sorted { $0.kept > $1.kept }
            LabeledContent("已存", value: kept.isEmpty ? "还没有" : "\(kept.count) 篇 · \(ByteCountFormatter.string(fromByteCount: Int64(packs.bytes), countStyle: .file))")
                .accessibilityIdentifier("packs.kept")
            ForEach(kept, id: \.file) { e in
                Text(e.title).font(.footnote).foregroundStyle(.secondary).lineLimit(1)
            }
            if !packs.note.isEmpty {
                Text(packs.note).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("packs.note")
            }
            Button(packs.busy ? "正在存…" : "现在就存今天的") { Task { await packs.refresh(force: true) } }
                .disabled(packs.busy)
                .accessibilityIdentifier("packs.now")
            if !kept.isEmpty {
                Button("删掉存的录音", role: .destructive) { packs.clear() }
            }
        } header: {
            Text("存在手机上的录音")
        } footer: {
            Text("只用 Wi-Fi 下载，不用流量；晚上充电时也会自己存。存在这台手机上，空间不够时 iPhone 也可能先清掉。")
        }
    }
}
