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
    button.textContent = token.surface || "אין נתונים"
    button.dataset.selectionKey = selectionKey
    button.dataset.stableTokenKey = selectionKey
    button.setAttribute("lang", token.language === "aramaic" ? "arc" : "he")
    button.setAttribute("dir", "rtl")
    button.setAttribute("aria-pressed", String(selectionKey === selectedTokenKey || token.selected === true))
    button.title = `${selectionKey} · ${token.morphology_code ?? ""}`
    button.onclick = () => {
      setStateValue("selected_token_key", selectionKey)
    }
    root.appendChild(button)
  }
}
