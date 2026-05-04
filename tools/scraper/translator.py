"""CSS-to-XPath translator with ::text and ::attr() pseudo-element support.

Extracted from Scrapling (D4Vinci) - MIT License.
Original adapted from parsel library.
"""

from functools import lru_cache

from cssselect import HTMLTranslator as OriginalHTMLTranslator
from cssselect.xpath import ExpressionError, XPathExpr as OriginalXPathExpr
from cssselect.parser import Element, FunctionalPseudoElement, PseudoElement


class XPathExpr(OriginalXPathExpr):
    textnode: bool = False
    attribute: str | None = None

    @classmethod
    def from_xpath(cls, xpath: OriginalXPathExpr, textnode: bool = False, attribute: str | None = None):
        x = cls(path=xpath.path, element=xpath.element, condition=xpath.condition)
        x.textnode = textnode
        x.attribute = attribute
        return x

    def __str__(self):
        path = super().__str__()
        if self.textnode:
            if path == "*":
                path = "text()"
            elif path.endswith("::*/*"):
                path = path[:-3] + "text()"
            else:
                path += "/text()"
        if self.attribute is not None:
            if path.endswith("::*/*"):
                path = path[:-2]
            path += f"/@{self.attribute}"
        return path

    def join(self, combiner, other, *args, **kwargs):
        if not isinstance(other, XPathExpr):
            raise ValueError(f"Cannot join non-XPathExpr: {type(other)}")
        super().join(combiner, other, *args, **kwargs)
        self.textnode = other.textnode
        self.attribute = other.attribute
        return self


class TranslatorMixin:
    """Adds ::text and ::attr() pseudo-element support to cssselect."""

    def xpath_element(self, selector: Element) -> XPathExpr:
        xpath = super().xpath_element(selector)
        return XPathExpr.from_xpath(xpath)

    def xpath_pseudo_element(self, xpath: OriginalXPathExpr, pseudo_element: PseudoElement) -> OriginalXPathExpr:
        if isinstance(pseudo_element, FunctionalPseudoElement):
            method_name = f"xpath_{pseudo_element.name.replace('-', '_')}_functional_pseudo_element"
            method = getattr(self, method_name, None)
            if not method:
                raise ExpressionError(f"Unknown pseudo-element ::{pseudo_element.name}()")
            xpath = method(xpath, pseudo_element)
        else:
            method_name = f"xpath_{pseudo_element.replace('-', '_')}_simple_pseudo_element"
            method = getattr(self, method_name, None)
            if not method:
                raise ExpressionError(f"Unknown pseudo-element ::{pseudo_element}")
            xpath = method(xpath)
        return xpath

    @staticmethod
    def xpath_attr_functional_pseudo_element(xpath: OriginalXPathExpr, function: FunctionalPseudoElement) -> XPathExpr:
        if function.argument_types() not in (["STRING"], ["IDENT"]):
            raise ExpressionError(f"Expected a single string/ident for ::attr(), got {function.arguments!r}")
        return XPathExpr.from_xpath(xpath, attribute=function.arguments[0].value)

    @staticmethod
    def xpath_text_simple_pseudo_element(xpath: OriginalXPathExpr) -> XPathExpr:
        return XPathExpr.from_xpath(xpath, textnode=True)


class HTMLTranslator(TranslatorMixin, OriginalHTMLTranslator):
    def css_to_xpath(self, css: str, prefix: str = "descendant-or-self::") -> str:
        return super().css_to_xpath(css, prefix)


_translator = HTMLTranslator()


@lru_cache(maxsize=256)
def css_to_xpath(query: str) -> str:
    """Convert a CSS selector (with optional ::text/::attr() extensions) to XPath."""
    return _translator.css_to_xpath(query)
