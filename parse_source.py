import os
import re
import requests
import sys

import BeautifulSoup

CACHE_RESULTS = True

DESCRIPTIONS_URL = "https://voparis-confluence.obspm.fr/display/VES/EPN-TAP+v2+parameter+description"


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


def make_formatter(template):
	"""returns a formatter using template.

	That's a function filling a formatted content into a template
	with a single %s.
	"""
	def formatter(el):
		if el.contents:
			body = format_to_TeX(el.contents)
		else:
			body = ""
		return template%body
	
	return formatter


LATEX_FORMATTERS = {
	"p": make_formatter("%s\n\n"),
	"em": make_formatter("\\emph{%s}"),
	"u": make_formatter("\\emph{%s}"),
	"strong": make_formatter("\\textbf{%s}"),
	"br": make_formatter("%s\\\\\n"),
	"ul": make_formatter("\\begin{itemize}%s\end{itemize}\n"),
	"li": make_formatter("\\item %s\n"),
	"pre": make_formatter("\begin{verbatim}%s\end{verbatim}"),
	"span": make_formatter("%s"),  # TODO: figure out what this is
	"div": make_formatter("\n\n%s\n\n"),  # TODO: figure out what this is
	"a": make_formatter("%s\\footnote{TODO:URL here}"),
	"table": make_formatter("\\begin{tabular}%s\end{tabular}"),
	"colgroup": make_formatter("???%s"),
	"col": make_formatter("???%s"),
	"tbody": make_formatter("%s"),
	"tr": make_formatter("%s\\\\"),
	"td": make_formatter("%s&"),
}


def format_to_TeX(elements):
	"""returns BeautifulSoup elements in LaTeX.
	"""
	for el in elements:
		if isinstance(el, BeautifulSoup.NavigableString):
			emit(el.string)
		else:
			emit(LATEX_FORMATTERS[el.name](el))


def main():
	soup = BeautifulSoup.BeautifulSoup(get_with_cache(DESCRIPTIONS_URL))
	for h1 in soup.findAll("h1"):
		emit("\\subsection{%s}\n\n"%h1.text)
		for h2 in find_siblings_until(h1, "h2", "h1"):
			emit("\\subsubsection{%s}\n\n"%h1.text)
			for h3 in find_siblings_until(h2, "h3", "h2"):
				emit("\\paragraph(%s)\n\n"%h3.text)
				format_to_TeX(collect_siblings_until(h3,
					frozenset(["h1", "h2", "h3"])))


if __name__=="__main__":
		main()
