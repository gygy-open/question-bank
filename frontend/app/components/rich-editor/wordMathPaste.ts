import { MathMLToLaTeX } from 'mathml-to-latex'

/**
 * 纯前端 Word 数学公式粘贴：把剪贴板 HTML 里的 OMML / MathML 转成 LaTeX，
 * 再替换为 Tiptap mathematics 扩展识别的占位元素
 * （`span[data-type="inline-math"]` / `div[data-type="block-math"]`，均带 `data-latex`）。
 *
 * 设计要点：
 * - OMML → MathML 用自研 DOM 遍历（AGPL 兼容，不依赖 Microsoft OMML2MML.XSL，
 *   也不依赖浏览器 XSLTProcessor，故可在 happy-dom/Vitest 中直接测试）。
 * - MathML → LaTeX 复用 mathml-to-latex（MIT）。
 * - Word 以 text/html 解析后，OMML 元素的 `localName` 形如 `m:f`（保留前缀、全小写），
 *   因此统一用 stripPrefix 归一，兼容 HTML 与 XML 两种解析结果。
 */

/** 剪贴板 HTML 是否包含 Word OMML 或 MathML 公式（廉价同步判断，供粘贴前快速拦截）。 */
export function htmlHasMath(html: string): boolean {
    // 仅匹配真实存在的 OMML/MathML 元素；Word 每次粘贴都会声明 math 命名空间，
    // 单凭命名空间判断会误拦所有 Word 粘贴，故不据此判定。
    return /<\s*m:oMath|<\s*math[\s/>]/i.test(html)
}

function stripPrefix(el: Element): string {
    return el.localName.replace(/^[^:]*:/, '').toLowerCase()
}

function childrenByName(el: Element | null, name: string): Element[] {
    if (!el) return []
    return Array.from(el.children).filter((c) => stripPrefix(c) === name)
}

function childByName(el: Element | null, name: string): Element | null {
    return childrenByName(el, name)[0] ?? null
}

/** 读取 OMML 属性值：HTML 解析后属性名带前缀（`m:val`），XML 解析后为 `val`。 */
function getVal(el: Element | null): string | null {
    if (!el) return null
    return el.getAttribute('m:val') ?? el.getAttribute('val')
}

function esc(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
}

function row(inner: string): string {
    return `<mrow>${inner}</mrow>`
}

/** 把一段文本切成 mn/mi/mo 记号，交给 mathml-to-latex 生成合理的 LaTeX。 */
function convertText(text: string): string {
    let out = ''
    const re = /(\d+\.?\d*)|([A-Za-z\u0370-\u03FF]+)|(\s+)|([^\s])/g
    let m: RegExpExecArray | null
    while ((m = re.exec(text))) {
        if (m[1]) out += `<mn>${esc(m[1])}</mn>`
        else if (m[2]) out += `<mi>${esc(m[2])}</mi>`
        else if (m[3]) continue
        else out += `<mo>${esc(m[4]!)}</mo>`
    }
    return out
}

function convertChildren(el: Element | null): string {
    if (!el) return ''
    return Array.from(el.children).map(convertElement).join('')
}

function convertRun(el: Element): string {
    const textElements = Array.from(el.getElementsByTagName('*')).filter(
        (child) => stripPrefix(child) === 't',
    )
    const text = textElements.length
        ? textElements.map((child) => child.textContent ?? '').join('')
        : (el.textContent ?? '')
    return convertText(text)
}

function convertFraction(el: Element): string {
    const num = row(convertChildren(childByName(el, 'num')))
    const den = row(convertChildren(childByName(el, 'den')))
    return `<mfrac>${num}${den}</mfrac>`
}

function convertScript(el: Element, tag: string, slots: string[]): string {
    const parts = slots.map((s) => row(convertChildren(childByName(el, s)))).join('')
    return `<${tag}>${parts}</${tag}>`
}

function isOn(val: string | null): boolean {
    return val === '1' || val === 'on' || val === 'true'
}

function convertRadical(el: Element): string {
    const pr = childByName(el, 'radpr')
    const degHidden = isOn(getVal(childByName(pr, 'deghide')))
    const base = row(convertChildren(childByName(el, 'e')))
    const degInner = convertChildren(childByName(el, 'deg'))
    if (!degHidden && degInner.trim()) {
        return `<mroot>${base}${row(degInner)}</mroot>`
    }
    return `<msqrt>${base}</msqrt>`
}

function convertNary(el: Element): string {
    const pr = childByName(el, 'narypr')
    const chr = getVal(childByName(pr, 'chr')) ?? '\u222B' // 默认 n-ary 符号为积分号
    const op = `<mo>${esc(chr)}</mo>`
    const subInner = convertChildren(childByName(el, 'sub'))
    const supInner = convertChildren(childByName(el, 'sup'))
    let opPart: string
    if (subInner.trim() && supInner.trim()) {
        opPart = `<msubsup>${op}${row(subInner)}${row(supInner)}</msubsup>`
    } else if (subInner.trim()) {
        opPart = `<msub>${op}${row(subInner)}</msub>`
    } else if (supInner.trim()) {
        opPart = `<msup>${op}${row(supInner)}</msup>`
    } else {
        opPart = op
    }
    return row(`${opPart}${row(convertChildren(childByName(el, 'e')))}`)
}

function convertDelimiter(el: Element): string {
    const pr = childByName(el, 'dpr')
    const begEl = childByName(pr, 'begchr')
    const endEl = childByName(pr, 'endchr')
    const sepEl = childByName(pr, 'sepchr')
    const beg = begEl ? (getVal(begEl) ?? '') : '('
    const end = endEl ? (getVal(endEl) ?? '') : ')'
    const sep = sepEl ? (getVal(sepEl) ?? '') : '|'
    const inner = childrenByName(el, 'e')
        .map((e) => row(convertChildren(e)))
        .join(sep ? `<mo>${esc(sep)}</mo>` : '')
    const begMo = beg ? `<mo>${esc(beg)}</mo>` : ''
    const endMo = end ? `<mo>${esc(end)}</mo>` : ''
    return row(`${begMo}${inner}${endMo}`)
}

function convertFunc(el: Element): string {
    const name = row(convertChildren(childByName(el, 'fname')))
    const arg = row(convertChildren(childByName(el, 'e')))
    return row(`${name}${arg}`)
}

function convertAccent(el: Element): string {
    const pr = childByName(el, 'accpr')
    const chr = getVal(childByName(pr, 'chr')) ?? '\u0302' // 默认重音为组合抑扬符（帽子）
    const base = row(convertChildren(childByName(el, 'e')))
    return `<mover>${base}<mo>${esc(chr)}</mo></mover>`
}

function convertBar(el: Element): string {
    const pr = childByName(el, 'barpr')
    const pos = getVal(childByName(pr, 'pos'))
    const base = row(convertChildren(childByName(el, 'e')))
    if (pos === 'bot') {
        return `<munder>${base}<mo>\u005F</mo></munder>`
    }
    return `<mover>${base}<mo>\u00AF</mo></mover>`
}

function convertMatrix(el: Element): string {
    const rows = childrenByName(el, 'mr')
        .map((r) => {
            const cells = childrenByName(r, 'e')
                .map((c) => `<mtd>${row(convertChildren(c))}</mtd>`)
                .join('')
            return `<mtr>${cells}</mtr>`
        })
        .join('')
    return `<mtable>${rows}</mtable>`
}

function convertElement(el: Element): string {
    switch (stripPrefix(el)) {
        case 'omath':
        case 'omathpara':
            return convertChildren(el)
        case 'r':
            return convertRun(el)
        case 'f':
            return convertFraction(el)
        case 'ssup':
            return convertScript(el, 'msup', ['e', 'sup'])
        case 'ssub':
            return convertScript(el, 'msub', ['e', 'sub'])
        case 'ssubsup':
            return convertScript(el, 'msubsup', ['e', 'sub', 'sup'])
        case 'rad':
            return convertRadical(el)
        case 'nary':
            return convertNary(el)
        case 'd':
            return convertDelimiter(el)
        case 'func':
            return convertFunc(el)
        case 'acc':
            return convertAccent(el)
        case 'bar':
            return convertBar(el)
        case 'm':
            return convertMatrix(el)
        case 'e':
        case 'num':
        case 'den':
        case 'sub':
        case 'sup':
        case 'deg':
        case 'fname':
            return row(convertChildren(el))
        default:
            // 未知包装元素（如 rPr/naryPr 等属性节点由各转换器单独读取）——递归其子节点。
            return convertChildren(el)
    }
}

/** 把一个 OMML 元素（m:oMath / m:oMathPara）转换成 MathML 字符串。 */
export function ommlElementToMathML(el: Element): string {
    return `<math xmlns="http://www.w3.org/1998/Math/MathML">${row(convertChildren(el))}</math>`
}

/** MathML 字符串 → LaTeX（异常时返回空串，交由调用方决定回退）。 */
export function mathmlToLatex(mathml: string): string {
    try {
        return MathMLToLaTeX.convert(mathml).trim()
    } catch {
        return ''
    }
}

/** 把单个 OMML 元素直接转成 LaTeX。 */
export function ommlElementToLatex(el: Element): string {
    return mathmlToLatex(ommlElementToMathML(el))
}

/** Word 把可编辑 OMML 放在 msEquation 条件注释中，浏览器默认只会得到 Comment。 */
export function revealWordEquationComments(html: string): string {
    return html.replace(
        /<!--\s*\[if\s+gte\s+msEquation\s+\d+\]\s*>([\s\S]*?)<!\s*\[endif\]\s*-->/gi,
        '$1',
    )
}

type MathHit = { el: Element; block: boolean }

function collectMath(root: Element, hits: MathHit[]): void {
    for (const el of Array.from(root.children)) {
        const name = stripPrefix(el)
        if (name === 'omathpara') {
            hits.push({ el, block: true })
        } else if (name === 'omath') {
            hits.push({ el, block: false })
        } else if (name === 'math') {
            hits.push({ el, block: el.getAttribute('display') === 'block' })
        } else {
            collectMath(el, hits)
        }
    }
}

function makeMathEl(doc: Document, latex: string, block: boolean): Element {
    const tag = block ? 'div' : 'span'
    const node = doc.createElement(tag)
    node.setAttribute('data-type', block ? 'block-math' : 'inline-math')
    node.setAttribute('data-latex', latex)
    return node
}

/**
 * 把 Word 剪贴板 HTML 中的 OMML / MathML 替换为 Tiptap 可解析的公式占位元素，
 * 返回可直接交给 `insertContentAt` 的 HTML 字符串。图片等其它内容原样保留（由上层决定是否忽略）。
 */
export function wordHtmlToTiptapHtml(html: string): string {
    const revealedHtml = revealWordEquationComments(html)
    const doc = new DOMParser().parseFromString(revealedHtml, 'text/html')
    const hits: MathHit[] = []
    collectMath(doc.body, hits)
    for (const { el, block } of hits) {
        const latex =
            stripPrefix(el) === 'math'
                ? mathmlToLatex(el.outerHTML)
                : ommlElementToLatex(el)
        if (latex) {
            el.replaceWith(makeMathEl(doc, latex, block))
        } else {
            el.replaceWith(doc.createTextNode(el.textContent ?? ''))
        }
    }
    return doc.body.innerHTML
}
