export default function (component) {
  const { data, parentElement, setStateValue } = component
  const root = parentElement.querySelector(".hebrew-token-selector")
  if (!root) return

  const tokens = Array.isArray(data?.tokens) ? data.tokens : []
  const selectedTokenKey = String(data?.selected_token_key ?? "")

  root.replaceChildren()

  let previousVerseKey = ""
  for (const token of tokens) {
    const selectionKey = String(token.selection_key ?? "")
    const wordIndex = Number(token.word_index)
    const verseKey = `${token.book ?? ""}:${token.chapter ?? ""}:${token.verse ?? ""}`

    if (verseKey !== previousVerseKey && token.verse !== undefined && token.verse !== null) {
      const marker = document.createElement("span")
      marker.className = "hebrew-verse-marker"
      marker.textContent = String(token.verse)
      root.appendChild(marker)
      previousVerseKey = verseKey
    }

    const button = document.createElement("button")
    button.type = "button"
    button.className = "hebrew-token"
    button.textContent = token.surface || "nincs adat"
    button.dataset.selectionKey = selectionKey
    button.dataset.stableTokenKey = selectionKey
    button.dataset.wordIndex = String(wordIndex)
    button.setAttribute("lang", token.language === "aramaic" ? "arc" : "he")
    button.setAttribute("dir", "rtl")
    button.setAttribute("aria-pressed", String(selectionKey === selectedTokenKey || token.selected === true))
    button.title = `${selectionKey} · ${token.strong_id ?? ""} · ${token.morphology_code ?? ""}`
    button.onclick = () => {
      setStateValue("selected_token_key", selectionKey)
      setStateValue("selected_word_index", wordIndex)
      setStateValue("verse", Number(token.verse))
      setStateValue("strong_id", String(token.strong_id ?? ""))
      setStateValue("surface", String(token.surface ?? ""))
    }
    root.appendChild(button)
  }
}
