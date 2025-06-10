import argparse
import dataclasses
import filecmp
import os
import pathlib
import yaml
from termcolor import cprint

@dataclasses.dataclass
class Mapping:
    name: str
    source: str
    dest: str

class Mappings:
    def __init__(self, cfg_dir: pathlib.Path, data: dict):
        self._mappings = list()
        for (s,d) in data.items():
            ls = cfg_dir / s
            hd = os.path.expanduser(os.path.join("~", d))
            self._mappings.append(Mapping(s,ls,hd))

    def items(self):
        for item in self._mappings:
            yield item

    @classmethod
    def from_yaml(cls, filename: pathlib.Path):
        with open(filename) as fs:
            idata = yaml.safe_load(fs)
            return cls(filename.parent, idata)

def exists(m: Mapping):
    if os.path.exists(m.dest):
        return True
    else:
        return False

def clear(m: Mapping, *, dry_run: bool = False):
    if dry_run:
        cprint(f'{m.name}: Remove destination file: {m.dest}', 'yellow')
        return

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

def linkfile(m: Mapping, *, dry_run: bool=False):
    cprint(f'{m.name}: linking {m.dest} -> {m.source}', 'yellow')
    if dry_run:
        return

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
        type=pathlib.Path,
        default=os.getcwd(),
    )
    parser.add_argument("-n", "--dry-run",
        action="store_true",
        help="Only print actions to be taken",
    )
    return parser

def main():
    parser = mk_argparser()
    args = parser.parse_args()
    try:
        input_file = args.dir / 'files.yaml'
        if not input_file.exists():
            raise RuntimeError(f"'files.yaml' input not found in '{args.dir}'")
        maps = Mappings.from_yaml(input_file)
        for m in maps.items():
            if exists(m):
                if has_diff(m):
                    cprint(f'{m.name}: Different file already exists at: {m.dest}', 'red')
                    if clear(m, dry_run=args.dry_run):
                        linkfile(m, dry_run=args.dry_run)
                else:
                    cprint(f'{m.name}: Up to date', 'green')
            else:
                linkfile(m, dry_run=args.dry_run)
    except Exception as e:
        print(e)

if __name__ == "__main__":
    main()
