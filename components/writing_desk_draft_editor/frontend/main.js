const ALLOWED_TAGS = new Set(["P", "BR", "STRONG", "B", "EM", "I", "U", "UL", "OL", "LI"])
const DROP_WITH_CONTENT = new Set(["SCRIPT", "STYLE", "NOSCRIPT"])
const instances = new WeakMap()
const DEBOUNCE_MS = 350

function clientSanitize(html) {
  const template = document.createElement("template")
  template.innerHTML = String(html || "")
  const walk = (node) => {
    ;[...node.childNodes].forEach((child) => {
      if (child.nodeType === Node.ELEMENT_NODE) {
        if (DROP_WITH_CONTENT.has(child.tagName)) {
          child.remove()
          return
        }
        walk(child)
        if (!ALLOWED_TAGS.has(child.tagName)) {
          child.replaceWith(...child.childNodes)
          return
        }
        while (child.attributes.length) {
          child.removeAttribute(child.attributes[0].name)
        }
      }
    })
  }
  walk(template.content)
  return template.innerHTML
}

function createInstance(parentElement, setStateValue) {
  const editor = parentElement.querySelector(".wd-draft-surface")
  const toolbar = parentElement.querySelector(".wd-draft-toolbar")
  if (!editor || !toolbar) {
    return null
  }

  let lastRevision = null
  let lastSent = null
  let debounceTimer = null
  const doc = parentElement.ownerDocument || document
  try {
    doc.execCommand("defaultParagraphSeparator", false, "p")
  } catch (_err) {
    /* contenteditable fallback: Chrome otherwise prefers <div> */
  }

  const currentHtml = () => editor.innerHTML

  const flushNow = () => {
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    const html = currentHtml()
    if (html === lastSent) return
    lastSent = html
    setStateValue("html", html)
  }

  const flushDebounced = () => {
    if (debounceTimer !== null) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(flushNow, DEBOUNCE_MS)
  }

  const onPointerDownCapture = (event) => {
    if (!parentElement.contains(event.target)) {
      flushNow()
    }
  }

  editor.addEventListener("input", flushDebounced)
  editor.addEventListener("blur", flushNow)
  editor.addEventListener("paste", (event) => {
    event.preventDefault()
    const clipboard = event.clipboardData
    const html = clipboard ? clipboard.getData("text/html") : ""
    const text = clipboard ? clipboard.getData("text/plain") : ""
    const cleaned = html ? clientSanitize(html) : ""
    if (cleaned) {
      doc.execCommand("insertHTML", false, cleaned)
    } else {
      doc.execCommand("insertText", false, text || "")
    }
    flushNow()
  })

  toolbar.querySelectorAll("button[data-cmd]").forEach((button) => {
    button.addEventListener("mousedown", (event) => {
      event.preventDefault()
    })
    button.addEventListener("click", () => {
      const command = button.getAttribute("data-cmd")
      editor.focus()
      doc.execCommand(command, false, null)
      flushNow()
    })
  })

  doc.addEventListener("pointerdown", onPointerDownCapture, true)

  return {
    sync(data) {
      const revision = Number(data?.revision ?? 0)
      const nextHtml = data?.html == null ? "" : String(data.html)
      const shouldReplace =
        lastRevision === null || Number.isNaN(revision) || revision !== lastRevision
      if (shouldReplace) {
        const firstMount = lastRevision === null
        if (editor.innerHTML !== nextHtml) {
          editor.innerHTML = nextHtml
        }
        lastRevision = revision
        lastSent = nextHtml
        if (!firstMount) {
          setStateValue("html", nextHtml)
        }
      }
    },
    flush: flushNow,
    destroy() {
      flushNow()
      if (debounceTimer !== null) {
        clearTimeout(debounceTimer)
        debounceTimer = null
      }
      doc.removeEventListener("pointerdown", onPointerDownCapture, true)
    },
  }
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  let inst = instances.get(parentElement)
  if (!inst) {
    inst = createInstance(parentElement, setStateValue)
    if (!inst) return
    instances.set(parentElement, inst)
  }
  inst.sync(data)
  return () => {
    inst.flush()
  }
}
