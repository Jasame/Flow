package cn.flowlang.app

import android.net.Uri

/** The one site this app opens: https://flow.jasa.hk (beta) or https://flowlang.cn (prod), from the flavor. */
object Site {
    val origin: String = BuildConfig.SITE.trimEnd('/')
    val host: String = Uri.parse(origin).host.orEmpty()

    /** The WebView's own User-Agent with "FlowAndroid/<version>" at the end; MainActivity sets it. */
    @Volatile
    var userAgent: String = "FlowAndroid/${BuildConfig.FLOW_VERSION}"

    fun isOwn(uri: Uri?): Boolean = uri != null && uri.scheme == "https" && uri.host.equals(host, ignoreCase = true) &&
        (uri.port == -1 || uri.port == 443)

    fun isOwn(url: String?): Boolean = url != null && isOwn(Uri.parse(url))

    /** "/audio/us-f/x.mp4?v=3" → "https://<site>/audio/us-f/x.mp4?v=3"; a full https address is kept as it is. */
    fun abs(path: String): String = when {
        path.startsWith("https://") -> path
        path.startsWith("/") -> origin + path
        else -> "$origin/$path"
    }
}
