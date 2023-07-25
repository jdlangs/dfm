import dataclasses
import filecmp
import os
import pathlib
import yaml

MAPPINGS_FILE = "files.yaml"

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

def check(m: Mapping):
    print(f'{m.name}: File already exists at destination: {m.dest}')
    if filecmp.cmp(m.source, m.dest):
        print(f'     Files are equal')
    else:
        print(f'     Files are different')

def linkfile(m: Mapping):
    print(f'{m.name}: linking {m.dest} -> {m.source}')
    dest = pathlib.Path(m.dest)
    if not dest.parent.exists():
        dest.parent.mkdir(parents=True)
    os.symlink(m.source, m.dest)

def main():
    maps = Mappings.from_yaml(MAPPINGS_FILE)
    for m in maps.items():
        if exists(m):
            check(m)
            if clear(m):
                linkfile(m)
        else:
            linkfile(m)

if __name__ == "__main__":
    main()
