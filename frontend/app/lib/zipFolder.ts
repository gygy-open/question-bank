import JSZip from 'jszip'

// Pack a folder selection (from a webkitdirectory input) into a single .zip File,
// preserving each file's relative path so markdown image refs still resolve server-side.
export async function zipFolder(files: FileList | File[], zipName = 'folder.zip'): Promise<File> {
  const zip = new JSZip()
  for (const file of Array.from(files)) {
    const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
    zip.file(path, file)
  }
  const blob = await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' })
  return new File([blob], zipName, { type: 'application/zip' })
}
