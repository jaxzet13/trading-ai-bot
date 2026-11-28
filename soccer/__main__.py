import sys


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    if a and a[0] == "laliga":
        from . import laliga
        laliga.run(dry="dry" in a)
    else:
        print("usage: python -m soccer laliga [dry]")


if __name__ == "__main__":
    main()
