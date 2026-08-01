import argparse


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args(argv)
    print(args.path)


if __name__ == "__main__":
    main()
