-- Pandoc Lua filter for Packt kobo/EPUB-HTML exports.
--
-- These sources wrap every text fragment in `[text]{#anchor .koboSpan ...}`
-- bracketed spans and encode page numbers in `.pagebreak`/`doc-pagebreak`
-- spans (aria-label = page label). Headers carry semantic classes
-- (chapterTitle, heading-1..3) rather than markdown levels.
--
-- This filter:
--   1. Unwraps every Span -> keeps inner text, drops the kobo attrs.
--   2. Emits `<!-- page N -->` for arabic pagebreak labels (roman = front
--      matter, dropped) so regex_pass.RE_PAGE can populate page_from/page_to.
--   3. Remaps header LEVEL by semantic class so chapter != section:
--        chapterTitle -> H1, heading-1 -> H2, heading-2 -> H3, heading-3 -> H4.
--      (chapterNumber is a span -> stays as a lone `# N`, merged downstream.)

local function classes_of(el)
  if el.classes then return table.concat(el.classes, " ") end
  return ""
end

function Span(el)
  local lbl  = el.attributes and el.attributes["aria-label"]
  local role = el.attributes and el.attributes["role"]
  local cls  = classes_of(el)
  if (role == "doc-pagebreak" or cls:find("pagebreak")) and lbl and lbl:match("^%d+$") then
    return pandoc.RawInline("markdown", "\n\n<!-- page " .. lbl .. " -->\n\n")
  end
  -- drop empty index/anchor spans entirely; otherwise unwrap to content
  return el.content
end

function Header(el)
  local cls = classes_of(el)
  if cls:find("chapterTitle") then
    el.level = 1
  elseif cls:find("heading%-1") or cls:find("mainHeading") then
    el.level = 2
  elseif cls:find("heading%-2") then
    el.level = 3
  elseif cls:find("heading%-3") then
    el.level = 4
  elseif cls:find("FM%-") then
    el.level = 2   -- front-matter headings (excluded by chapter line ranges)
  end
  el.attr = pandoc.Attr()  -- strip ids/classes from the header itself
  return el
end
