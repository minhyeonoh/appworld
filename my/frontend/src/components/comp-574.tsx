"use client";

import {
  expandAllFeature,
  hotkeysCoreFeature,
  selectionFeature,
  syncDataLoaderFeature,
} from "@headless-tree/core";
import { useTree } from "@headless-tree/react";
import {
  FolderIcon,
  FolderOpenIcon,
  ListCollapseIcon,
  ListTreeIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tree, TreeItem, TreeItemLabel } from "@/components/tree";

interface Item {
  name: string;
  children?: string[];
  fileExtension?: string;
}

const items: Record<string, Item> = {
  app: {
    children: ["app/layout.tsx", "app/page.tsx", "app/(dashboard)", "app/api"],
    name: "app",
  },
  "app/(dashboard)": {
    children: ["app/(dashboard)/dashboard"],
    name: "(dashboard)",
  },
  "app/(dashboard)/dashboard": {
    children: ["app/(dashboard)/dashboard/page.tsx"],
    name: "dashboard",
  },
  "app/(dashboard)/dashboard/page.tsx": {
    fileExtension: "tsx",
    name: "page.tsx",
  },
  "app/api": { children: ["app/api/hello"], name: "api" },
  "app/api/hello": { children: ["app/api/hello/route.ts"], name: "hello" },
  "app/api/hello/route.ts": { fileExtension: "ts", name: "route.ts" },
  "app/layout.tsx": { fileExtension: "tsx", name: "layout.tsx" },
  "app/page.tsx": { fileExtension: "tsx", name: "page.tsx" },
  components: {
    children: ["components/button.tsx", "components/card.tsx"],
    name: "components",
  },
  "components/button.tsx": { fileExtension: "tsx", name: "button.tsx" },
  "components/card.tsx": { fileExtension: "tsx", name: "card.tsx" },
  lib: { children: ["lib/utils.ts"], name: "lib" },
  "lib/utils.ts": { fileExtension: "ts", name: "utils.ts" },
  "next.config.mjs": { fileExtension: "mjs", name: "next.config.mjs" },
  "package.json": { fileExtension: "json", name: "package.json" },
  public: {
    children: ["public/favicon.ico", "public/vercel.svg"],
    name: "public",
  },
  "public/favicon.ico": { fileExtension: "ico", name: "favicon.ico" },
  "public/vercel.svg": { fileExtension: "svg", name: "vercel.svg" },
  "README.md": { fileExtension: "md", name: "README.md" },
  root: {
    children: [
      "app",
      "components",
      "lib",
      "public",
      "package.json",
      "tailwind.config.ts",
      "tsconfig.json",
      "next.config.mjs",
      "README.md",
    ],
    name: "Project Root",
  },
  "tailwind.config.ts": { fileExtension: "ts", name: "tailwind.config.ts" },
  "tsconfig.json": { fileExtension: "json", name: "tsconfig.json" },
};

const indent = 20;

export default function Component() {
  const tree = useTree<Item>({
    dataLoader: {
      getChildren: (itemId) => items[itemId].children ?? [],
      getItem: (itemId) => items[itemId],
    },
    features: [
      syncDataLoaderFeature,
      selectionFeature,
      hotkeysCoreFeature,
      expandAllFeature,
    ],
    getItemName: (item) => item.getItemData()?.name ?? "Unknown",
    indent,
    initialState: {
      expandedItems: ["app", "app/(dashboard)", "app/(dashboard)/dashboard"],
      selectedItems: ["components"],
    },
    isItemFolder: (item) => (item.getItemData()?.children?.length ?? 0) > 0,
    rootItemId: "root",
  });

  return (
    <div className="flex h-full flex-col gap-2 *:nth-2:grow">
      <div className="flex items-center gap-2">
        <Button onClick={() => tree.expandAll()} size="sm" variant="outline">
          <ListTreeIcon
            aria-hidden="true"
            className="-ms-1 opacity-60"
            size={16}
          />
          Expand all
        </Button>
        <Button onClick={tree.collapseAll} size="sm" variant="outline">
          <ListCollapseIcon
            aria-hidden="true"
            className="-ms-1 opacity-60"
            size={16}
          />
          Collapse all
        </Button>
      </div>

      <Tree 
        className="before:-ms-1 relative before:absolute before:inset-0 before:bg-[repeating-linear-gradient(to_right,transparent_0,transparent_calc(var(--tree-indent)-1px),var(--border)_calc(var(--tree-indent)-1px),var(--border)_calc(var(--tree-indent)))]" 
        indent={indent} 
        tree={tree}
      >
        {tree.getItems().map((item) => {
          return (
            <TreeItem item={item} key={item.getId()}>
              <TreeItemLabel className="bg-transparent before:-inset-y-0.5 before:-z-10 relative before:absolute before:inset-x-0 before:bg-sidebar">
                <span className="flex items-center gap-2">
                  {/* {item.isFolder() &&
                    (item.isExpanded() ? (
                      <FolderOpenIcon className="pointer-events-none size-4 text-muted-foreground" />
                    ) : (
                      <FolderIcon className="pointer-events-none size-4 text-muted-foreground" />
                    ))} */}
                  {item.getItemName()}
                  {item.isFolder() && (
                    <span className="-ms-1 text-muted-foreground">
                      {`(${item.getChildren().length})`}
                    </span>
                  )}
                </span>
              </TreeItemLabel>
            </TreeItem>
          );
        })}
      </Tree>
    </div>
  );
}
