package cn.flowlang.app.privacy

import android.annotation.SuppressLint
import android.app.Activity
import android.app.Dialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.res.ColorStateList
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.TextPaint
import android.text.method.LinkMovementMethod
import android.text.style.ClickableSpan
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import cn.flowlang.app.Accent
import cn.flowlang.app.R
import kotlinx.coroutines.CompletableDeferred

/**
 * What the learner sees of Consent: the question, its second look (基本模式), the two texts over it, and 撤回同意's check.
 * The texts come from this build (Consent.docs): nothing is opened on the network before the answer.
 */
class ConsentUi(private val a: Activity) {
    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), a.resources.displayMetrics).toInt()
    private fun night() = a.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES

    /**
     * The question → true for 同意. [why]: the line on top when a feature asked for it in 基本模式. On the [first] start,
     * 不同意 has a second look: 进入基本模式 (false), or 再看看 (the question again); in 基本模式 it just answers false.
     */
    suspend fun ask(why: String? = null, first: Boolean = true): Boolean {
        while (true) {
            if (question(why, first)) return true
            if (!first || basicChosen()) return false
        }
    }

    private suspend fun question(why: String?, first: Boolean): Boolean {
        val d = CompletableDeferred<Boolean>()
        val body = a.getString(R.string.consent_body) + a.getString(if (first) R.string.consent_tail_first else R.string.consent_tail_basic)
        val text = TextView(a).apply {
            text = linked(if (why != null) why + "\n\n" + body else body)
            textSize = 15f
            setLineSpacing(0f, 1.25f)
            setTextColor(a.getColor(R.color.flow_text))
            movementMethod = LinkMovementMethod.getInstance()
            setPadding(dp(24), dp(8), dp(24), dp(4))
        }
        Accent.dialog(a).setTitle(if (why != null) R.string.consent_title_feature else R.string.consent_title)
            .setView(ScrollView(a).apply { addView(text) })
            .setPositiveButton(R.string.consent_agree) { _, _ -> d.complete(true) }
            .setNegativeButton(R.string.consent_decline) { _, _ -> d.complete(false) }
            .setCancelable(false)
            .show()
        return d.await()
    }

    private suspend fun basicChosen(): Boolean {
        val d = CompletableDeferred<Boolean>()
        Accent.dialog(a).setTitle(R.string.consent_basic_title).setMessage(R.string.consent_basic_body)
            .setPositiveButton(R.string.consent_basic_go) { _, _ -> d.complete(true) }
            .setNegativeButton(R.string.consent_basic_back) { _, _ -> d.complete(false) }
            .setCancelable(false)
            .show()
        return d.await()
    }

    /** 撤回同意 (privacy.withdraw): what it does, then 撤回 → true. */
    suspend fun withdrawChosen(): Boolean {
        val d = CompletableDeferred<Boolean>()
        Accent.dialog(a).setTitle(R.string.withdraw_title).setMessage(R.string.withdraw_body)
            .setPositiveButton(R.string.withdraw_go) { _, _ -> d.complete(true) }
            .setNegativeButton(R.string.cancel) { _, _ -> d.complete(false) }
            .setOnCancelListener { d.complete(false) }
            .show()
        return d.await()
    }

    /** 《用户协议》 and 《隐私和数据》 open their text over the question, as the site's ticks do (B6 #290). */
    private fun linked(s: String): CharSequence {
        val b = SpannableStringBuilder(s)
        val color = Accent.color(a)
        for ((title, id) in listOf("《用户协议》" to "terms", "《隐私和数据》" to "privacy")) {
            var i = s.indexOf(title)
            while (i >= 0) {
                b.setSpan(object : ClickableSpan() {
                    override fun onClick(v: View) = showDoc(id)
                    override fun updateDrawState(ds: TextPaint) { ds.color = color; ds.isUnderlineText = false }
                }, i, i + title.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
                i = s.indexOf(title, i + title.length)
            }
        }
        return b
    }

    /**
     * One of the two texts over everything (the question too): 「← 返回」 and its title on top, 「返回」 at the end. A link
     * to the other text (or a part of one) opens it here; a link to a site opens the phone's browser when tapped.
     */
    @SuppressLint("SetJavaScriptEnabled")
    fun showDoc(id: String, anchor: String? = null) {
        val docs = Consent.docs(a)
        val night = night()
        val bg = a.getColor(R.color.flow_bg)
        val fg = a.getColor(R.color.flow_text)
        val accent = Accent.color(a)
        val d = Dialog(a, if (night) android.R.style.Theme_Material_NoActionBar else android.R.style.Theme_Material_Light_NoActionBar)
        val title = TextView(a).apply { textSize = 17f; setTypeface(typeface, Typeface.BOLD); setTextColor(fg); maxLines = 1 }
        val web = WebView(a)
        fun load(doc: String, at: String?) {
            val key = if (doc in Consent.DOCS) doc else Consent.DOCS[0]
            title.text = docs.titles[key]
            web.tag = at
            web.loadDataWithBaseURL("https://appassets.androidplatform.net/legal/", page(docs.html[key].orEmpty(), night, fg, bg, accent),
                "text/html", "utf-8", null)
        }
        web.settings.apply {
            javaScriptEnabled = true  // only to go to a part of a text (scrollIntoView): the page is this app's, its text escaped
            blockNetworkLoads = true
            allowFileAccess = false
            allowContentAccess = false
        }
        web.setBackgroundColor(bg)
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, r: WebResourceRequest): Boolean {
                val u = r.url
                when (u.scheme) {
                    "flow-doc" -> load(u.schemeSpecificPart.orEmpty(), u.fragment)
                    "https" -> try {
                        a.startActivity(Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE))
                    } catch (e: ActivityNotFoundException) { /* no browser */ }
                }
                return true
            }

            override fun onPageFinished(view: WebView, url: String?) {
                val at = (view.tag as? String)?.takeIf { Regex("g-[a-z0-9-]+").matches(it) } ?: return
                view.evaluateJavascript("var e=document.getElementById('$at');if(e)e.scrollIntoView()", null)
            }

            // the pages' process ended by the system (memory): this layer closes, the question stays
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                d.dismiss()
                return true
            }
        }
        val back = TextView(a).apply {
            text = a.getString(R.string.doc_back_arrow)
            textSize = 16f
            setTextColor(accent)
            setPadding(dp(16), dp(14), dp(12), dp(14))
            setOnClickListener { d.dismiss() }
        }
        val bar = LinearLayout(a).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(back)
            addView(title, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        val done = Button(a).apply {
            text = a.getString(R.string.doc_back)
            isAllCaps = false
            setTextColor(Color.WHITE)
            backgroundTintList = ColorStateList.valueOf(accent)
            setOnClickListener { d.dismiss() }
        }
        val col = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(bg)
            addView(bar)
            addView(web, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            addView(done, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
                .apply { setMargins(dp(16), dp(8), dp(16), dp(12)) })
        }
        ViewCompat.setOnApplyWindowInsetsListener(col) { v, insets ->
            val s = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            v.setPadding(s.left, s.top, s.right, s.bottom)
            WindowInsetsCompat.CONSUMED
        }
        d.setContentView(col)
        d.window?.let { w ->
            w.setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
            w.setBackgroundDrawable(android.graphics.drawable.ColorDrawable(bg))
            WindowCompat.setDecorFitsSystemWindows(w, false)
            @Suppress("DEPRECATION") run { w.statusBarColor = Color.TRANSPARENT; w.navigationBarColor = Color.TRANSPARENT }
            WindowCompat.getInsetsController(w, w.decorView).apply {
                isAppearanceLightStatusBars = !night
                isAppearanceLightNavigationBars = !night
            }
        }
        d.setOnDismissListener { (web.parent as? ViewGroup)?.removeView(web); web.destroy() }
        load(id, anchor)
        d.show()
    }

    /** The chapter as the site's guide shows it (its .guide-body look), in the app's colours. */
    private fun page(body: String, night: Boolean, fg: Int, bg: Int, accent: Int): String {
        fun hex(c: Int) = String.format("#%06X", 0xFFFFFF and c)
        val line = if (night) "rgba(232,238,234,.18)" else "rgba(27,36,32,.14)"
        val soft = if (night) "rgba(232,238,234,.06)" else "rgba(27,36,32,.045)"
        return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
html{color-scheme:${if (night) "dark" else "light"}}
body{margin:0;padding:2px 20px 28px;font:16px/1.75 sans-serif;color:${hex(fg)};background:${hex(bg)};overflow-wrap:anywhere}
h3{font-size:17px;line-height:1.5;margin:24px 0 6px}
p{margin:10px 0}ul,ol{padding-left:22px;margin:8px 0}li{margin:4px 0}b{font-weight:600}
a{color:${hex(accent)};text-decoration:none}.dead{color:inherit}
table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.6;margin:12px 0}
th,td{border:1px solid $line;padding:6px 8px;text-align:left;vertical-align:top}th{background:$soft}
.tip{border-left:3px solid ${hex(accent)};background:$soft;padding:6px 12px;margin:12px 0}
kbd{font:inherit;border:1px solid $line;border-radius:4px;padding:0 4px}pre{white-space:pre-wrap}
</style></head><body>$body</body></html>"""
    }
}
