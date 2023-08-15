import argparse
import dataclasses
import filecmp
import os
import pathlib
import yaml

@dataclasses.dataclass
class Mapping:
    name: str
    source: str
    dest: str

class Mappings:
    def __init__(self, data: dict):
        self._mappings = list()
        for (s,d) in data.items():
            ls = os.path.join(os.getcwd(), s)
            hd = os.path.expanduser(os.path.join("~", d))
            self._mappings.append(Mapping(s,ls,hd))

    def items(self):
        for item in self._mappings:
            yield item

    @classmethod
    def from_yaml(cls, filename):
        with open(filename) as fs:
            idata = yaml.safe_load(fs)
            return cls(idata)

def exists(m: Mapping):
    if os.path.exists(m.dest):
        return True
    else:
        return False

def clear(m: Mapping):
    i = input(f'{m.name}: Remove destination file: {m.dest} ? (y/N)')
    if i == 'y':
        os.remove(m.dest)
        return True
    else:
        return False

def has_diff(m: Mapping):
    if filecmp.cmp(m.source, m.dest):
        return False
    else:
        return True

def linkfile(m: Mapping):
    print(f'{m.name}: linking {m.dest} -> {m.source}')
    dest = pathlib.Path(m.dest)
    if not dest.parent.exists():
        dest.parent.mkdir(parents=True)
    os.symlink(m.source, m.dest)

def mk_argparser():
    parser = argparse.ArgumentParser(
        description="DotFile Manager"
    )
    parser.add_argument("dir",
        help="Directory with files.yaml mappings list, default current dir",
        nargs="?",
        default=os.getcwd(),
    )
    return parser

def main():
    parser = mk_argparser()
    args = parser.parse_args()
    try:
        maps = Mappings.from_yaml(os.path.join(args.dir, 'files.yaml'))
        for m in maps.items():
            if exists(m):
                if has_diff(m):
                    print(f'{m.name}: Different file already exists at destination: {m.dest}')
                    if clear(m):
                        linkfile(m)
                else:
                    print(f'{m.name}: Already up to date')
            else:
                linkfile(m)
    except Exception as e:
        print(e)

if __name__ == "__main__":
    main()
