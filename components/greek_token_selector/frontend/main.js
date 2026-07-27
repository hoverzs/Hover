export default function (component) {
  const { data, parentElement, setStateValue } = component
  const root = parentElement.querySelector(".greek-token-selector")
  if (!root) return

  const tokens = Array.isArray(data?.tokens) ? data.tokens : []
  const selectedTokenKey = String(data?.selected_token_key ?? data?.selected_word_index ?? "")

  root.replaceChildren()

  for (const token of tokens) {
    const wordIndex = Number(token.word_index)
    const selectionKey = String(token.selection_key ?? wordIndex)
    const button = document.createElement("button")
    button.type = "button"
    button.className = "greek-token"
    button.textContent = token.greek_form || "nincs adat"
    button.dataset.wordIndex = String(wordIndex)
    button.dataset.selectionKey = selectionKey
    button.setAttribute("aria-pressed", String(selectionKey === selectedTokenKey))
    button.onclick = () => {
      setStateValue("selected_token_key", selectionKey)
      setStateValue("selected_word_index", wordIndex)
    }
    root.appendChild(button)
  }
}
