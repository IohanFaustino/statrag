import { describe, it, expect } from "vitest";
import { extractImageUrls, imageFilename } from "./exportZip";

describe("extractImageUrls", () => {
  it("extracts /api, /img and http(s) image links", () => {
    const md = [
      "![a](/api/figures?path=x.jpg)",
      "![b](/img/fig.png)",
      "![c](https://example.com/p.png)",
    ].join("\n\n");
    expect(extractImageUrls(md)).toEqual([
      "/api/figures?path=x.jpg",
      "/img/fig.png",
      "https://example.com/p.png",
    ]);
  });

  it("dedupes a repeated url, first-seen order", () => {
    const md = "![a](/img/x.png)\n\n![again](/img/x.png)\n\n![b](/img/y.png)";
    expect(extractImageUrls(md)).toEqual(["/img/x.png", "/img/y.png"]);
  });

  it("ignores plain links and data URIs", () => {
    const md = "[text](/api/foo) and ![d](data:image/png;base64,AAAA)";
    expect(extractImageUrls(md)).toEqual([]);
  });

  it("extracts the url when an image has a title attribute", () => {
    expect(extractImageUrls('![a](/img/x.png "a title")')).toEqual(["/img/x.png"]);
  });
});

describe("imageFilename", () => {
  it("uses the url basename + a stable short hash + extension", () => {
    const a = imageFilename("/img/scatter.png");
    expect(a).toMatch(/^scatter-[a-z0-9]+\.png$/);
    expect(imageFilename("/img/scatter.png")).toBe(a);
  });

  it("derives extension from content type when url has none", () => {
    expect(imageFilename("/api/figures?path=x", "image/jpeg")).toMatch(/\.jpg$/);
  });

  it("falls back to figure + img extension", () => {
    expect(imageFilename("/api/figures?path=")).toMatch(/^figure-[a-z0-9]+\.img$/);
  });

  it("different urls with same basename get different names", () => {
    const a = imageFilename("/a/fig.png");
    const b = imageFilename("/b/fig.png");
    expect(a).not.toBe(b);
  });

  it("takes only the basename of a slash-containing path param", () => {
    const url = "/api/figures?path=%2Fhome%2Fiohan%2FRAG%2Fmedia%2Fimage_rsrcD3S.jpg";
    expect(imageFilename(url)).toMatch(/^image_rsrcD3S-[a-z0-9]+\.jpg$/);
  });
});

import JSZip from "jszip";
import { buildZipBlob } from "./exportZip";

// Build a fake fetch that returns a tiny image for listed urls, 404 otherwise.
function fakeFetch(ok: Record<string, string>): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url in ok) {
      return {
        ok: true,
        headers: { get: (h: string) => (h.toLowerCase() === "content-type" ? ok[url] : null) },
        arrayBuffer: async () => new TextEncoder().encode("IMGBYTES").buffer,
      } as unknown as Response;
    }
    return { ok: false, status: 404, headers: { get: () => null }, arrayBuffer: async () => new ArrayBuffer(0) } as unknown as Response;
  }) as typeof fetch;
}

describe("buildZipBlob", () => {
  it("bundles fetched images and rewrites their links to images/…", async () => {
    const md = "![a](/img/x.png)\n\n![b](/api/figures?path=y.jpg)";
    const fetchFn = fakeFetch({ "/img/x.png": "image/png", "/api/figures?path=y.jpg": "image/jpeg" });
    const { blob, missing } = await buildZipBlob(md, { docName: "doc" }, fetchFn);
    expect(missing).toEqual([]);
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    const names = Object.keys(zip.files).sort();
    expect(names).toContain("doc.md");
    const imgs = names.filter((n) => n.startsWith("images/") && !n.endsWith("/"));
    expect(imgs).toHaveLength(2);
    const text = await zip.file("doc.md")!.async("string");
    expect(text).toContain("](images/");
    expect(text).not.toContain("](/img/x.png)");
    expect(text).not.toContain("](/api/figures?path=y.jpg)");
  });

  it("fetches a repeated url once and rewrites both occurrences", async () => {
    const md = "![a](/img/x.png)\n\n![again](/img/x.png)";
    const { blob } = await buildZipBlob(md, { docName: "doc" }, fakeFetch({ "/img/x.png": "image/png" }));
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    expect(Object.keys(zip.files).filter((n) => n.startsWith("images/") && !n.endsWith("/"))).toHaveLength(1);
    const text = await zip.file("doc.md")!.async("string");
    expect(text.match(/\]\(images\//g)).toHaveLength(2);
    expect(text).not.toContain("/img/x.png");
  });

  it("keeps the link and lists missing for a failed fetch", async () => {
    const md = "![ok](/img/x.png)\n\n![bad](/img/missing.png)";
    const { blob, missing } = await buildZipBlob(md, { docName: "doc" }, fakeFetch({ "/img/x.png": "image/png" }));
    expect(missing).toEqual(["/img/missing.png"]);
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    expect(Object.keys(zip.files).filter((n) => n.startsWith("images/") && !n.endsWith("/"))).toHaveLength(1);
    const text = await zip.file("doc.md")!.async("string");
    expect(text).toContain("](/img/missing.png)");
    expect(text).toContain("](images/");
  });

  it("zips just the md when there are no images", async () => {
    const { blob, missing } = await buildZipBlob("no images here", { docName: "doc" }, fakeFetch({}));
    expect(missing).toEqual([]);
    const zip = await JSZip.loadAsync(await blob.arrayBuffer());
    expect(Object.keys(zip.files)).toEqual(["doc.md"]);
  });
});
