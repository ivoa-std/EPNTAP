# -*- coding: utf-8 -*

import os
import re
import requests
import sys

from bs4 import BeautifulSoup, NavigableString

# URL of the long parameter descriptions
DESCRIPTIONS_URL = ("https://voparis-confluence.obspm.fr/display"
  "/VES/EPN-TAP+v2+parameter+description")
# URL of the document with the metadata table
TABLE_URL = ("https://voparis-confluence.obspm.fr/display/VES"
  "/EPN-TAP+V2.0+parameters")

# Headers of DESCRIPTIONS sections that must be skipped
IGNORED_SECTIONS = frozenset([
  "Europlanet2020-RI/VESPA Discussions Board",
  "EPN-TAP v2 parameter description",
])


# a global state variable (really only used to kill dumb breaks;
# breaks suck)
ELEMENT_STACK = []

# set to false in operation (for development only)
CACHE_RESULTS = False



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
  if not isinstance(s, bytes):
    s = s.encode("utf-8")
  os.write(sys.stdout.fileno(), s)


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
    ).replace("}" , "\\}" 
    ).replace("{" , "\\{" 
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
  if "UDR" in literal:
    # it's the level table
    return ("\\begingroup\small"
      +literal.replace(" (std data format)", ""
        ).replace("llllllll}", "lllllllp{0.35\\textwidth}}"
        ).replace(r"\textbf{EPN-TAP }\textbf{v2}", 
          r"\vbox{\vskip 2pt\hbox{\bf EPN-}\vskip 3pt\hbox{TAP2}}")
      +"\\endgroup")
  else:
    raise Exception("Unknown table: {}".format(literal))


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
      format_el(child) for child in row_el.findAll(re.compile("t[dh]"))
      )+"\\\\"

  parts = ["\\begin{inlinetable}",
    "\\begin{tabular}{%s}"%("l"*len(rows[0].findAll(re.compile("t[dh]")))),
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


def format_a(el):
  """formats a a link as anchor plus footnote.
  """
  return "%s\\footnote{\\\\url{%s}}"%(
    format_to_TeX(el.contents),
    escape_LaTeX(el["href"]))


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
  "b": make_formatter("\\textbf{%s}"),
  "strong": make_formatter("\\textbf{%s}"),
  "br": format_br,
  "ul": make_formatter("\\begin{itemize}\n%s\\end{itemize}\n\n"),
  "li": make_formatter("\\item %s\n"),
  "pre": make_formatter("\\begin{verbatim}%s\\end{verbatim}"),
  "span": make_formatter("%s"),  # TODO: figure out what this is
  "div": make_formatter("\n\n%s\n\n"),  # TODO: figure out what this is
  "a": format_a,
  "s": make_formatter("%s (\\textbf{Deleted})"),
  "table": format_table,
  "colgroup": make_formatter("???%s"),
  "col": make_formatter("???%s"),
  "tbody": make_formatter("%s"),
  "td": make_formatter("%s"),
  "th": make_formatter("%s"),
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
    if isinstance(el, NavigableString):
      accum.append(escape_LaTeX(el.string))
    else:
      accum.append(format_el(el))
  return "".join(accum)


def write_column_description():
  """writes a TeX formatted version of the long descriptions document.
  """
  soup = BeautifulSoup(get_with_cache(DESCRIPTIONS_URL), "html")
  for h1 in soup.find_all("h1"):
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


################# Column table below here

def is_stupid_header_row(row):
  """returns true if we believe row is what the EPN-TAP people used
  as section separators in the columns table.

  That is: the text is red:-)
  """
  try:
    perhaps_p = row.contents[0].contents[0]
    perhaps_span = perhaps_p.contents[0]
    if perhaps_span.get("style")=='color: rgb(255,0,0);':
      return True
  except (AttributeError, KeyError):
    pass  # Fall through to False
  return False


def iter_column_meta():
  """yields dictionaries with the EPN-TAP column metadata snarfed
  from TABLE_URL.
  """
  soup = BeautifulSoup(get_with_cache(TABLE_URL), "html")
  table = soup.find("table", 
    {"class": "wrapped relative-table confluenceTable"})

  col_labels = ["name", "mandatory", "type", "unit", "description", 
    "ucd", "ucd_obscore", "utype", "comments"]

  for row in table.findAll("tr"):
    first_cell = row.contents[0]
    if first_cell.name=="th":
      # Skip the header row
      continue

    # screw the stupid header lines
    elif is_stupid_header_row(row):
      yield {"headline": format_el(first_cell)}

    else:
      yield dict(zip(
          col_labels, 
          [format_el(e) for e in row.findAll("td")]))


def write_column_table():
  """write a TeX formatted rendering of the metadata table to stdout.
  """
  ELEMENT_STACK.append("table")
  emit("\\begingroup\\small")
  emit("\\begin{longtable}{p{3.5cm}p{0.5cm}p{1cm}p{1cm}p{7cm}"
    "p{3cm}}\n")
  head = ("\\sptablerule\n\\textbf{Name}"
    "&\\textbf{Req}"
    "&\\textbf{Type}"
    "&\\textbf{Unit}"
    "&\\textbf{Description}"
    "&\\textbf{UCD}\\\\"
    "\\sptablerule")
  emit("%s\\endfirsthead\n%s\\endhead\n"%(
    head, head))

  for rec in iter_column_meta():
    if "headline" in rec:
      emit("\\multicolumn{6}{c}{\\vrule width 0pt height 20pt depth 12pt"
        " \\textbf{%(headline)s}}\\\\\n"%rec)
    else:
      emit("%(name)s&%(mandatory)s&%(type)s&%(unit)s&%(description)s"
        "&%(ucd)s\\\\\n"%rec)

  emit("\\sptablerule\n")
  emit("\\end{longtable}\n")
  emit("\\endgroup\n")


if __name__=="__main__":
  what = None
  if len(sys.argv)==2:
    what = sys.argv[1]

  if what=="columntable":
    write_column_table()
  elif what=="columndescription":
    write_column_description()
  else:
    sys.stderr.write("Usage: %s columndescription|columntable\n")


# vi:ts=2:et:sta
