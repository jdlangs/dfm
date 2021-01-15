import dataclasses
import filecmp
import os
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

def clear(m: Mapping):
    if os.path.exists(m.dest):
        print(f'{m.name}: Removing destination file: {m.dest}')
        os.remove(m.dest)

def check(m: Mapping):
    if os.path.exists(m.dest):
        print(f'{m.name}: File already exists at destination: {m.dest}')
        if filecmp.cmp(m.source, m.dest):
            print(f'     Files are equal')
        else:
            print(f'     Files are different')
        return False
    return True

def linkfile(m: Mapping):
    print(f'{m.name}: linking {m.dest} -> {m.source}')
    os.symlink(m.source, m.dest)

def main():
    maps = Mappings.from_yaml(MAPPINGS_FILE)
    for m in maps.items():
        clear(m)
        if check(m):
            linkfile(m)

if __name__ == "__main__":
    main()
