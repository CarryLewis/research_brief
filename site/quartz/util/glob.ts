import path from "path"
import { FilePath } from "./path"
import { globby } from "globby"

export function toPosixPath(fp: string): string {
  return fp.split(path.sep).join("/")
}

export async function glob(
  pattern: string,
  cwd: string,
  ignorePatterns: string[],
): Promise<FilePath[]> {
  // gitignore:false so build-time synced content/ (gitignored) is still published.
  // Privacy exclusions live in quartz.config.ts ignorePatterns + sync-content.sh.
  const fps = (
    await globby(pattern, {
      cwd,
      ignore: ignorePatterns,
      gitignore: false,
    })
  ).map(toPosixPath)
  return fps as FilePath[]
}
