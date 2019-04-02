# -*- coding: utf-8 -*

import os
import re
import requests
import sys

import BeautifulSoup

# URL of the long parameter descriptions
DESCRIPTIONS_URL = ("https://voparis-confluence.obspm.fr/display"
  "/VES/EPN-TAP+v2+parameter+description")
# URL of the document with the metadata table
TABLE_URL = ("https://voparis-confluence.obspm.fr/display/VES/"
  "EPN-TAP+v2+parameter+description")

# Headers of DESCRIPTIONS sections that must be skipped
IGNORED_SECTIONS = frozenset([
  "Europlanet2020-RI/VESPA Discussions Board",
  "EPN-TAP v2 parameter description",
])


# a global state variable (really only used to kill dumb breaks;
# breaks suck)
ELEMENT_STACK = []

# set to false in operation (for development only)
CACHE_RESULTS = True



def get_with_cache(url, bypassCache=False):
  cacheName = re.sub("[^\w]+", "", url)+".cache"
  if not bypassCache and CACHE_RESULTS and os.path.exists(cacheName):
    doc = open(cacheName).read()
  else:
    req = requests.get(url)
    doc = req.content
    if CACHE_RESULTS:
      with open(cacheName, "w") as f:
        f.write(doc)
  return doc


def emit(s):
  """adds a string s to the output result.
  """
  if s is None:
    raise Exception("Attempting to emit a None")
  if isinstance(s, unicode):
    s = s.encode("utf-8")
  sys.stdout.write(s)


def find_siblings_until(element, sibling_type, stop_sibling):
  """yields siblings of to sibling_type until stop_sibling is
  encountered (or the document ends).

  This is used to collect headings of a certain level and thus
  construct the document structure.
  """
  while True:
    element = element.nextSibling
    if element is None:
      break
    elif not hasattr(element, "name"):
      continue
    elif element.name==sibling_type:
      yield element
    elif element.name==stop_sibling:
      break


def collect_siblings_until(element, stop_set):
  """returns a list of all siblings of element until something in
  stop_set is encountered (or the document ends).

  stop_set must be a set of element type names (like h1, h2...).
  """
  collection = []
  while True:
    element = element.nextSibling
    if element is None:
      break
    elif hasattr(element, "name") and element.name in stop_set:
      break
    else:
      collection.append(element)
  return collection


def escape_LaTeX(s):
  """returns s with LaTeX active characters replaced.

  I also take the liberty of improving quotes when I can get them.
  """
  return re.sub('"([^"]+)"', r"``\1''",
    s.replace( "\\" , "$\\backslash$" 
    ).replace("&" , "\\&" 
    ).replace("#" , "\\#" 
    ).replace("%" , "\\%" 
    ).replace("_" , "\\_"))


def make_formatter(template):
  """returns a formatter using template.

  That's a function filling a formatted content into a template
  with a single %s; this works for make HTML elements, but some
  need custom handling.
  """
  def formatter(el):
    if el.contents:
      body = format_to_TeX(el.contents)
    else:
      body = ""
    return template%body
  
  return formatter


def hack_table(literal):
  """returns a LaTeX table literal hacked based on knowledge that
  we have about a table.

  Ugh.  Let's see how we can deal with this mess later.
  """
  if "CODMAC" in literal:
    # it's the level table
    return ("\\begingroup\small"
      +literal.replace(" (std data format)", ""
        ).replace("llllllll}", "lllllllp{0.35\\textwidth}}"
        ).replace(r"\textbf{EPN-TAP }\textbf{v2}", 
          r"\vbox{\vskip 2pt\hbox{\bf EPN-}\vskip 3pt\hbox{TAP2}}")
      +"\\endgroup")


def format_table(el):
  """A formatter for (halfway sane) tables.

  This doesn't do nested tables or anything else not well behaved,
  and the resulting tables aren't terribly pretty.  This also
  assumes that the first tr has the table headings.

  For non-trivial tables, you'll probably need to enable special
  handling using; let's see how to do it if we really get more tables.
  """
  rows = el.findAll("tr")
  if not rows:
    # empty table, don't care
    return

  def format_one_row(row_el):
    return "&".join(
      format_el(child) for child in row_el.findAll("td"))+"\\\\"

  parts = ["\\begin{inlinetable}",
    "\\begin{tabular}{%s}"%("l"*len(rows[0].findAll("td"))),
    "\\sptablerule"]
  parts.extend([
    format_one_row(rows[0]),
    "\\sptablerule\n"])

  for row in rows[1:]:
    parts.append(format_one_row(row))

  parts.extend(["\\end{tabular}",
    "\\end{inlinetable}"])

  return hack_table("\n".join(parts))


def format_br(el):
  """makes a break if we think LaTeX won't balk on it.

  This uses global state; we inhibit breaks within tables and at the
  top level.
  """
  if ELEMENT_STACK==['br'] or "table" in ELEMENT_STACK:
    return ""
  else:
    return "\\\\"


def format_p(el):
  """formats a paragraph.

  The main thing here is that confluence has p tags within table cells.
  These, we want to suppress.
  """
  if "table" in ELEMENT_STACK:
    return format_to_TeX(el.contents)
  else:
    return "%s\n\n"%format_to_TeX(el.contents)


LATEX_FORMATTERS = {
  "p": format_p,
  "em": make_formatter("\\emph{%s}"),
  "u": make_formatter("\\emph{%s}"),
  "strong": make_formatter("\\textbf{%s}"),
  "br": format_br,
  "ul": make_formatter("\\begin{itemize}\n%s\\end{itemize}\n\n"),
  "li": make_formatter("\\item %s\n"),
  "pre": make_formatter("\\begin{verbatim}%s\\end{verbatim}"),
  "span": make_formatter("%s"),  # TODO: figure out what this is
  "div": make_formatter("\n\n%s\n\n"),  # TODO: figure out what this is
  "a": make_formatter("%s\\footnote{TODO:URL here}"),
  "table": format_table,
  "colgroup": make_formatter("???%s"),
  "col": make_formatter("???%s"),
  "tbody": make_formatter("%s"),
  "td": make_formatter("%s"),
  "h1": make_formatter("\\subsection{%s}\n\n"),
  "h2": make_formatter("\\subsubsection{%s}\n\n"),
  "h3": make_formatter("\\paragraph{%s}\n\n"),
}


def format_el(el):
  """returns TeX for a BeautifulSoup element el.

  This dispatches based on LATEX_FORMATTERS.
  """
  ELEMENT_STACK.append(el.name)
  try:
    return LATEX_FORMATTERS[el.name](el)
  finally:
    ELEMENT_STACK.pop()


def format_to_TeX(elements):
  """returns BeautifulSoup elements in LaTeX.
  """
  accum = []
  for el in elements:
    if isinstance(el, BeautifulSoup.NavigableString):
      accum.append(escape_LaTeX(el.string))
    else:
      accum.append(format_el(el))
  return "".join(accum)


def main():
  soup = BeautifulSoup.BeautifulSoup(get_with_cache(DESCRIPTIONS_URL),
    convertEntities="html")
  for h1 in soup.findAll("h1"):
    if h1.text in IGNORED_SECTIONS:
      continue
    emit(
      "%% To ignore the following section, add '%s' to IGNORED_SECTIONS\n"%
      h1.text)

    emit(format_el(h1))
    for h2 in find_siblings_until(h1, "h2", "h1"):
      emit(re.sub("\d\d?- ", "", format_el(h2)))
      for h3 in find_siblings_until(h2, "h3", "h2"):
        emit(format_el(h3))
        emit(format_to_TeX(collect_siblings_until(h3,
          frozenset(["h1", "h2", "h3"]))))


if __name__=="__main__":
    main()

# vi:ts=2:et:sta
