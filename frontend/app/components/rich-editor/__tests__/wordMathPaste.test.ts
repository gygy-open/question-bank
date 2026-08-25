import { describe, it, expect } from 'vitest'
import {
    htmlHasMath,
    mathmlToLatex,
    ommlElementToMathML,
    ommlElementToLatex,
    revealWordEquationComments,
    wordHtmlToTiptapHtml,
} from '../wordMathPaste'

function parseFirstElement(html: string): Element {
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return doc.body.firstElementChild as Element
}

describe('htmlHasMath', () => {
    it('检测 OMML（oMath）', () => {
        expect(htmlHasMath('<p><m:oMath><m:r><m:t>x</m:t></m:r></m:oMath></p>')).toBe(true)
    })
    it('检测 OMML（oMathPara 显示公式）', () => {
        expect(htmlHasMath('<p><m:oMathPara><m:oMath></m:oMath></m:oMathPara></p>')).toBe(true)
    })
    it('检测 MathML', () => {
        expect(htmlHasMath('<p><math><mi>x</mi></math></p>')).toBe(true)
    })
    it('仅声明 math 命名空间但无公式元素时返回 false（避免误拦所有 Word 粘贴）', () => {
        expect(
            htmlHasMath(
                '<html xmlns:m="http://schemas.../officeDocument/2006/math"><body><p>纯文本</p></body></html>',
            ),
        ).toBe(false)
    })
    it('普通 HTML 返回 false', () => {
        expect(htmlHasMath('<p>hello <b>world</b></p>')).toBe(false)
    })
})

describe('mathmlToLatex (MathML → LaTeX)', () => {
    it('转换分数', () => {
        const latex = mathmlToLatex(
            '<math><mfrac><mrow><mi>a</mi></mrow><mrow><mi>b</mi></mrow></mfrac></math>',
        )
        expect(latex).toBe('\\frac{a}{b}')
    })
    it('转换上标', () => {
        const latex = mathmlToLatex(
            '<math><msup><mrow><mi>a</mi></mrow><mrow><mn>2</mn></mrow></msup></math>',
        )
        expect(latex).toContain('a^')
        expect(latex).toContain('2')
    })
    it('转换失败返回空串', () => {
        expect(mathmlToLatex('<not-mathml')).toBe('')
    })
})

describe('OMML → MathML → LaTeX', () => {
    it('分数 a/b', () => {
        const el = parseFirstElement(
            '<m:oMath><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num><m:den><m:r><m:t>b</m:t></m:r></m:den></m:f></m:oMath>',
        )
        expect(ommlElementToMathML(el)).toContain('<mfrac>')
        expect(ommlElementToLatex(el)).toBe('\\frac{a}{b}')
    })

    it('上标 x^2', () => {
        const el = parseFirstElement(
            '<m:oMath><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath>',
        )
        const latex = ommlElementToLatex(el)
        expect(latex).toContain('x^')
        expect(latex).toContain('2')
    })

    it('下标 x_i', () => {
        const el = parseFirstElement(
            '<m:oMath><m:sSub><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub></m:oMath>',
        )
        const latex = ommlElementToLatex(el)
        expect(latex).toContain('x')
        expect(latex).toContain('_')
        expect(latex).toContain('i')
    })

    it('平方根 sqrt(x)（degHide）', () => {
        const el = parseFirstElement(
            '<m:oMath><m:rad><m:radPr><m:degHide m:val="on"/></m:radPr><m:deg></m:deg><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad></m:oMath>',
        )
        expect(ommlElementToMathML(el)).toContain('<msqrt>')
        expect(ommlElementToLatex(el)).toContain('\\sqrt')
    })

    it('n 次根 mroot（含次数）', () => {
        const el = parseFirstElement(
            '<m:oMath><m:rad><m:deg><m:r><m:t>3</m:t></m:r></m:deg><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad></m:oMath>',
        )
        expect(ommlElementToMathML(el)).toContain('<mroot>')
    })

    it('n-ary 求和携带上下限', () => {
        const el = parseFirstElement(
            '<m:oMath><m:nary><m:naryPr><m:chr m:val="\u2211"/></m:naryPr>' +
                '<m:sub><m:r><m:t>i</m:t></m:r></m:sub>' +
                '<m:sup><m:r><m:t>n</m:t></m:r></m:sup>' +
                '<m:e><m:r><m:t>i</m:t></m:r></m:e></m:nary></m:oMath>',
        )
        const mathml = ommlElementToMathML(el)
        expect(mathml).toContain('<msubsup>')
        expect(mathml).toContain('\u2211')
    })

    it('未知/属性节点被跳过而不报错', () => {
        const el = parseFirstElement(
            '<m:oMath><m:r><m:rPr><m:sty m:val="p"/></m:rPr><m:t>a+b</m:t></m:r></m:oMath>',
        )
        expect(ommlElementToLatex(el)).toContain('a')
        expect(ommlElementToLatex(el)).toContain('b')
    })

    it('支持 Word HTML 中直接或经 span/i 包装的 m:r 文本', () => {
        const el = parseFirstElement(
            '<m:oMath><m:r>f</m:r><m:r><span><i>x</i></span></m:r><m:r>=1</m:r></m:oMath>',
        )
        const latex = ommlElementToLatex(el)
        expect(latex).toContain('f')
        expect(latex).toContain('x')
        expect(latex).toContain('=')
        expect(latex).toContain('1')
    })
})

describe('Word msEquation 条件注释', () => {
    const clipboardHtml = `
        <p>函数
        <!--[if gte msEquation 12]><m:oMath>
            <m:r><span><i>f</i></span></m:r>
            <m:d><m:e><m:r>x</m:r></m:e></m:d>
            <m:r>=</m:r>
            <m:f>
                <m:num><m:r>1</m:r></m:num>
                <m:den><m:r><m:rPr><m:nor/></m:rPr>ln</m:r><m:r>x</m:r></m:den>
            </m:f>
        </m:oMath><![endif]-->
        </p>`

    it('显露被条件注释隐藏的 OMML', () => {
        const revealed = revealWordEquationComments(clipboardHtml)
        expect(revealed).toContain('<m:oMath>')
        expect(revealed).not.toContain('[if gte msEquation')
    })

    it('把真实 Word 条件注释公式转换为 Tiptap 公式节点', () => {
        const out = wordHtmlToTiptapHtml(clipboardHtml)
        expect(out).toContain('data-type="inline-math"')
        expect(out).toContain('data-latex=')
        expect(out).not.toContain('m:oMath')
        expect(out).not.toContain('[if gte msEquation')
    })
})

describe('wordHtmlToTiptapHtml', () => {
    it('把 OMML 显示公式替换为 block-math div', () => {
        const html =
            '<p><m:oMathPara><m:oMath><m:f><m:num><m:r><m:t>a</m:t></m:r></m:num>' +
            '<m:den><m:r><m:t>b</m:t></m:r></m:den></m:f></m:oMath></m:oMathPara></p>'
        const out = wordHtmlToTiptapHtml(html)
        expect(out).toContain('data-type="block-math"')
        expect(out).toContain('data-latex="\\frac{a}{b}"')
        expect(out).not.toContain('oMath')
    })

    it('把行内 OMML 替换为 inline-math span 并保留周围文本', () => {
        const html =
            '<p>结果是 <m:oMath><m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e>' +
            '<m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup></m:oMath> 。</p>'
        const out = wordHtmlToTiptapHtml(html)
        expect(out).toContain('data-type="inline-math"')
        expect(out).toContain('结果是')
        expect(out).toContain('。')
        expect(out).not.toContain('oMath')
    })

    it('MathML display=block 映射为 block-math', () => {
        const html =
            '<p><math display="block"><mfrac><mrow><mi>a</mi></mrow><mrow><mi>b</mi></mrow></mfrac></math></p>'
        const out = wordHtmlToTiptapHtml(html)
        expect(out).toContain('data-type="block-math"')
        expect(out).toContain('\\frac{a}{b}')
    })

    it('MathML 默认（无 display）映射为 inline-math', () => {
        const html = '<p><math><mi>x</mi></math></p>'
        const out = wordHtmlToTiptapHtml(html)
        expect(out).toContain('data-type="inline-math"')
    })

    it('转换失败时保留公式可见文本', () => {
        const html = '<p>公式：<math><unsupported>x + y</unsupported></math></p>'
        const out = wordHtmlToTiptapHtml(html)
        expect(out).toContain('公式：')
        expect(out).toContain('x + y')
    })
})
