function addNonceToScripts(markup: string, nonce: string) {
  return markup
    .replace(/<script\b([^>]*?)\snonce=""([^>]*?)>/g, `<script$1 nonce="${nonce}"$2>`)
    .replace(/<script\b(?![^>]*\snonce=)/g, `<script nonce="${nonce}"`)
}

export default defineNitroPlugin((nitroApp) => {
  nitroApp.hooks.hook('render:html', (html, { event }) => {
    const nonce = event.context.nonce
    if (!nonce) return

    html.head = html.head.map((entry) => addNonceToScripts(entry, nonce))
    html.body = html.body.map((entry) => addNonceToScripts(entry, nonce))
    html.bodyAppend = html.bodyAppend.map((entry) => addNonceToScripts(entry, nonce))
  })
})