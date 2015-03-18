#!/usr/bin/python

import argparse
import subprocess

def maybe_char(s, i):
    if i < len(s):
        return s[i]
    return ''

def process_line(line):
    linenew = ""
    i = 0
    num_spaces = 0
    while i < len(line):
        c = line[i]
        if c == ' ':
            num_spaces += 1
            stripped = linenew.strip()
            if (len(stripped) == 0 or
                not (stripped[-1].isalnum() or
                     (stripped[-1] == '>' and not stripped[-2:] == " >"))):
                # Ignore whitespace at the start of the line or after
                # non-alphanumeric characters. Things like:
                #
                #    *foo = bar;
                #   ^
                #
                #    int *foo, *foo = bar;
                #             ^
                # Note that we want to convert Foo<bar> *foo, but
                # not Foo > *bar.
                i += 1
                continue

            if stripped.endswith("return") or stripped.endswith("sizeof"):
                # Don't turn |return *a| into |return* a|, same for sizeof.
                i += 1
                continue

            # look for one or more '*' or '&' chars.
            after_sigils = i + 1
            while maybe_char(line, after_sigils) in ('&', '*'):
                after_sigils += 1
            if after_sigils == i + 1:
                i += 1
                continue

            nextchar = maybe_char(line, after_sigils)
            if nextchar in ('/', ' '):
                # Ignore "*/" (end of comment) and "* " (as in a * b).
                i += 1
                continue

            # Comments often include things like: "Foo *or* bar". Ignore if we're
            # followed by a number of alphanumeric chars + '*'. Yes, this is a poor
            # man's regular expression.
            j = after_sigils
            while maybe_char(line, j).isalnum():
                j += 1
            if maybe_char(line, j) == '*':
                i += 1
                continue

            sigils = line[i+1:after_sigils]
            if sigils == "&&" and line[after_sigils:].strip() == "":
                # |Foo &| or |Foo *| at the end of a line is turned into
                # |Foo&| or |Foo*|, but we don't do this for && as it
                # leads to false positives like this:
                #
                #   |x > Y &&| -> |X > Y&&|
                i += 1
                continue

            if sigils in ("*", "&") and maybe_char(line, after_sigils) == '=':
                # Don't turn A *= b into A* = b. Same for &=.
                i += 1
                continue

            # OK, we have a match. Copy the sigils.
            linenew += sigils

            if nextchar.isalpha() or nextchar == '_':
                # Insert the spaces at the other side of the sigils. Only do this
                # if we're followed by an identifier, to avoid:
                #
                # - Trailing whitespace when we do |Foo *| -> |Foo* |
                # - Foo<Bar *> should become Foo<Bar*>
                # - Likewise for these two cases: f(Foo *, Bar &) -> f(Foo*, Bar&)

                # Edge case: if we found more than one space, subtract the number of
                # sigils we found, to handle this case correctly:
                #
                #     int     foo;
                #     char    **bar;
                #
                # If we don't special-case this, it'd become:
                #
                #     int     foo;
                #     char**    bar;
                num_sigils = after_sigils - (i + 1)
                assert num_sigils > 0
                if num_spaces > 1:
                    num_spaces -= num_sigils
                if num_spaces < 1:
                    num_spaces = 1
                linenew += ' ' * num_spaces
            i = after_sigils
            num_spaces = 0
        else:
            linenew += ' ' * num_spaces
            num_spaces = 0
            linenew += c
            i += 1
    return linenew

def run_tests():
    print "Running tests..."

    cases = [
        # Simple cases.
        ("A *a", "A* a"),
        ("char ****p", "char**** p"),
        ("A &b", "A& b"),
        ("Foo *&x = y", "Foo*& x = y"),

        ("A<B *>", "A<B*>"),
        ("A *", "A*"),
        ("A ***\n", "A***\n"),
        ("A &", "A&"),
        ("sizeof(A *)", "sizeof(A*)"),

        # Should not convert mul or and operations.
        ("Xa * y", "Xa * y"),
        ("Xa & z", "Xa & z"),

        # Should preserve amount of whitespace as best as possible.
        ("AA     *foo", "AA*    foo"),
        ("AA     *****foo", "AA***** foo"),

        # Should not turn comments like |a *or* b| into |a* or* b|.
        ("// a *or* b", "// a *or* b"),

        # Some special cases.
        ("return *foo", "return *foo"),
        ("sizeof *n", "sizeof *n"),
        ("  *x = y;", "  *x = y;"),

        ("x > 0 &&", "x > 0 &&"),
        ("x > 0 && yy", "x > 0 && yy"),
        ("a &= b", "a &= b"),
        ("a *= b", "a *= b"),

        ("foo > bar &&", "foo > bar &&"),
        ("foo > bar &&\n", "foo > bar &&\n"),

        ("Foo<Bar *> *foo", "Foo<Bar*>* foo"),
        ("Foo<Bar *> &foo", "Foo<Bar*>& foo"),
        ("Foo<Bar ***> &foo", "Foo<Bar***>& foo"),
        ("Foo<Bar ***> *&foo", "Foo<Bar***>*& foo"),
        ("Foo > *bar", "Foo > *bar"),
    ]

    for inp, expected in cases:
        res = process_line(inp)
        assert res == expected, "Failed: |" + inp + "| -> |" + res + "|"

    print "Tests passed"

directories = [
    "js/src",
    "js/public",
    "js/xpconnect",
    "js/ipc"
]

def should_restyle(filename):
    if not filename.endswith(".h") and not filename.endswith(".cpp"):
        return False
    for d in directories:
        if filename.startswith(d):
            return True
    return False

def process_file(filename):
    print "Processing " + filename + "..."
    result = ""
    with open(filename) as f:
        for line in f:
            result += process_line(line)
    with open(filename, 'wb') as f:
        f.write(result)

def main():
    parser = argparse.ArgumentParser(description='Restyle SpiderMonkey et al ;-)')
    parser.add_argument('--tree', dest='restyle_tree', action='store_true',
                        help='Restyle JS/XPConnect directories. Should be run from root of hg clone.')
    parser.add_argument('--files', metavar='FILE', help='A file to be restyled',
                        nargs='*')
    args = parser.parse_args()

    run_tests()

    if args.restyle_tree:
        print "Restyling tree..."
        p = subprocess.Popen(['hg', 'manifest', '-q'], stdout=subprocess.PIPE)
        out, err = p.communicate()

        filenames = out.split()
        for filename in filenames:
            if not should_restyle(filename):
                continue
            process_file(filename)
    elif args.files:
        for filename in args.files:
            process_file(filename)

if __name__ == "__main__":
    main()
