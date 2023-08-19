import pydoc
import sys
from typing import Callable, List, Tuple, Union

from plum.signature import Signature
from plum.util import TypeHint

__all__ = ["AmbiguousLookupError", "NotFoundLookupError"]


class AmbiguousLookupError(LookupError):
    """A signature cannot be resolved due to ambiguity."""


class NotFoundLookupError(LookupError):
    """A signature cannot be resolved because no applicable method can be found."""


def _document(f: Callable) -> str:
    """Generate documentation for a function `f`.

    The generated documentation contains both the function definition and the
    docstring. The docstring is on the same level of indentation of the function
    definition. There will be no trailing newlines.

    If the package :mod:`sphinx` is not imported, then the function definition will
    be preceded by the string `<separator>`.

    If the package :mod:`sphinx` is imported, then the function definition will include
    a Sphinx directive to displays the function definition in a nice way.

    Args:
        f (function): Function.

    Returns:
        str: Documentation for `f`.
    """
    # :class:`pydoc._PlainTextDoc` removes styling. This styling will display
    # erroneously in Sphinx.
    parts = pydoc._PlainTextDoc().document(f).rstrip().split("\n")

    # Separate out the function definition and the lines corresponding to the body.
    title = parts[0]
    body = parts[1:]

    # Remove indentation from every line of the body. This indentation defaults to
    # four spaces.
    body = [line[4:] for line in body]

    # If `sphinx` is imported, assume that we're building the documentation. In that
    # case, display the function definition in a nice way.
    if "sphinx" in sys.modules:
        title = ".. py:function:: " + title + "\n   :noindex:"
    else:
        title = "<separator>\n\n" + title
    title += "\n"  # Add a newline to separate the title from the body.

    # Ensure that there are no trailing newlines. This can happen if the body is empty.
    return "\n".join([title] + body).rstrip()


class Resolver:
    """Method resolver.

    Attributes:
        signatures (list[:class:`.signature.Signature`]): Registered signatures.
        is_faithful (bool): Whether all signatures are faithful or not.
    """

    def __init__(self, owner, function_name: str):
        self.signatures: List[Signature] = []
        self.is_faithful: bool = True
        self.owner = owner
        self.function_name = function_name

    def doc(self, exclude: Union[Callable, None] = None) -> str:
        """Concatenate the docstrings of all methods of this function. Remove duplicate
        docstrings before concatenating.

        Args:
            exclude (function, optional): Exclude this implementation from the
                concatenation.

        Returns:
            str: Concatenation of all docstrings.
        """
        # Generate all docstrings, possibly excluding `exclude`.
        docs = [
            _document(sig.implementation)
            for sig in self.signatures
            if not (exclude and sig.implementation == exclude)
        ]
        # This can yield duplicates, because of extra methods automatically generated by
        # :func:`.signature.append_default_args`. We remove these by simply only
        # keeping unique docstrings.
        unique_docs = []
        for d in docs:
            if d not in unique_docs:
                unique_docs.append(d)
        # The unique documentations have no trailing newlines, so separate them with
        # a newline.
        return "\n\n".join(unique_docs)

    def register(self, signature: Signature) -> None:
        """Register a new signature.

        Args:
            signature (:class:`.signature.Signature`): Signature to add.
        """
        existing = [s == signature for s in self.signatures]
        if any(existing):
            if sum(existing) != 1:
                raise AssertionError(
                    f"The added signature `{signature}` is equal to {sum(existing)} "
                    f"existing signatures. This should never happen."
                )
            self.signatures[existing.index(True)] = signature
        else:
            self.signatures.append(signature)

        # Use a double negation for slightly better performance.
        self.is_faithful = not any(not s.is_faithful for s in self.signatures)

    def __len__(self) -> int:
        return len(self.signatures)

    def resolve(
        self, target: Union[Tuple[object, ...], Signature]
    ) -> Tuple[Callable, TypeHint]:
        """Find the method and return type for arguments.

        Args:
            target (object): Target.

        Returns:
            function: Method.
            type: Return type.
        """
        try:
            # Attempt to find the method using the resolver.
            signature = self._find_signature(target)
            return signature.implementation, signature.return_type
        except NotFoundLookupError as e:
            return self._handle_not_found_lookup_error(e)

    def _find_signature(
        self, target: Union[Tuple[object, ...], Signature]
    ) -> Signature:
        """Find the most specific signature that satisfies a target.

        Args:
            target (:class:`.signature.Signature` or tuple[object]): Target to resolve.
                Must be either a signature to be encompassed or a tuple of arguments.

        Returns:
            :class:`.signature.Signature`: The most specific signature satisfying
                `target`.
        """
        if isinstance(target, tuple):

            def check(s):
                # `target` are concrete arguments.
                return s.match(target)

        else:

            def check(s):
                # `target` is a signature that must be encompassed.
                return target <= s

        candidates = []
        for signature in [s for s in self.signatures if check(s)]:
            # If none of the candidates are comparable, then add the method as
            # a new candidate and continue.
            if not any(c.is_comparable(signature) for c in candidates):
                candidates += [signature]
                continue

            # The signature under consideration is comparable with at least one
            # of the candidates. First, filter any strictly more general candidates.
            new_candidates = [c for c in candidates if not signature < c]

            # If the signature under consideration is as specific as at least
            # one candidate, then and only then add it as a candidate.
            if any(signature <= c for c in candidates):
                candidates = new_candidates + [signature]
            else:
                candidates = new_candidates

        if len(candidates) == 0:
            # There is no matching signature.
            raise NotFoundLookupError(f"`{target}` could not be resolved.")
        elif len(candidates) == 1:
            # There is exactly one matching signature. Success!
            return candidates[0]
        else:
            # There are multiple matching signatures. Before raising an exception,
            # attempt to resolve the ambiguity using the precedence of the signatures.
            precedences = [c.precedence for c in candidates]
            max_precendence = max(precedences)
            if sum([p == max_precendence for p in precedences]) == 1:
                return candidates[precedences.index(max_precendence)]
            else:
                # Could not resolve the ambiguity, so error. First, make a nice list
                # of the candidates and their precedences.
                listed_candidates = "\n  ".join(
                    [f"{c} (precedence: {c.precedence})" for c in candidates]
                )
                raise AmbiguousLookupError(
                    f"`{target}` is ambiguous among the following:\n"
                    f"  {listed_candidates}"
                )

    def _handle_not_found_lookup_error(
        self, ex: NotFoundLookupError
    ) -> Tuple[Callable, TypeHint]:
        if not self.owner:
            # Not in a class. Nothing we can do.
            raise ex

        # In a class. Walk through the classes in the class's MRO, except for
        # this class, and try to get the method.
        method = None
        return_type = object

        for c in self.owner.__mro__[1:]:
            # Skip the top of the type hierarchy given by `object` and `type`.
            # We do not suddenly want to fall back to any unexpected default
            # behaviour.
            if c in {object, type}:
                continue

            # We need to check `c.__dict__` here instead of using `hasattr`
            # since e.g. `c.__le__` will return  even if `c` does not implement
            # `__le__`!
            if self.function_name in c.__dict__:
                method = getattr(c, self.function_name)
            else:
                # For some reason, coverage fails to catch the `continue`
                # below. Add the do-nothing `_ = None` fixes this.
                # TODO: Remove this once coverage properly catches this.
                _ = None
                continue

            # Ignore abstract methods.
            if getattr(method, "__isabstractmethod__", False):
                method = None
                continue

            # We found a good candidate. Break.
            break

        if not method:
            # If no method has been found after walking through the MRO, raise
            # the original exception.
            raise ex
        return method, return_type
