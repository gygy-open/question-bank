# File Preview

File Preview lets you view original DOCX and Markdown files directly in the browser without downloading them.

## Supported Formats

| Format | Rendering |
|------|---------|
| DOCX | Rendered in the browser with `docx-preview` |
| Markdown | Rendered by the built-in Markdown preview component |

## Usage

The preview page loads a file by its URL, determines the type from the extension, displays it inline, and provides a download link. It is commonly used to view the original materials of Smart Import.

::: tip
Previews are rendered by the frontend reading the file URL directly. Original files are stored in the upload directory (`backend/uploads` on the server edition; inside the data directory on the desktop edition).
:::
