
import useSWR from 'swr';
import { useEffect, useState } from 'react';
import {
  expandAllFeature,
  hotkeysCoreFeature,
  selectionFeature,
  syncDataLoaderFeature,
} from "@headless-tree/core";
import { useTree } from "@headless-tree/react";
import { Tree, TreeItem, TreeItemLabel } from "@/components/tree";

const fetcher = (url) => fetch(url).then((res) => res.json());
export function TaskFinder({ onSelect, selectedExp, selectedTask }) {
  const { data: items, error } = useSWR("http://localhost:8000/tasks", fetcher, {
    refreshInterval: 2000,
  });
  if (!items) return <div className="p-4 text-xs text-muted-foreground">Loading file system...</div>;
  if (error) return <div className="p-4 text-xs text-red-500">Failed to load tasks.</div>;
  return (
    <TaskTree 
      items={items} 
      onSelect={onSelect} 
      selectedExp={selectedExp} 
      selectedTask={selectedTask} 
    />
  );
}

const indent = 20;
function TaskTree({ items, onSelect, selectedExp, selectedTask }) {
  const [selectedItems, setSelectedItems] = useState<string[]>([]);
  const [focusedItem, setFocusedItem] = useState<string | null>(null);

  const tree = useTree<Item>({
    state: { selectedItems, focusedItem },
    setSelectedItems,
    setFocusedItem,
    dataLoader: {
      getChildren: (itemId) => items?.[itemId]?.children ?? [],
      getItem: (itemId) => items?.[itemId],
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
      expandedItems: [],
      selectedItems: [],
    },
    isItemFolder: (item) => (item.getItemData()?.children?.length ?? 0) > 0,
    rootItemId: "/",
  });

  useEffect(() => {
    if (!focusedItem) return;
    const parts = focusedItem.split("/");
    const taskId = parts.pop();
    if (parts.pop() === "tasks") {
      const experimentName = parts.join("/").substring(1);
      if (experimentName !== selectedExp || taskId !== selectedTask) {
        onSelect(experimentName, taskId);
      }
    }
  }, [focusedItem, onSelect, selectedExp, selectedTask]);

  return (
    <Tree 
      className="before:-ms-1 relative before:absolute before:inset-0 before:bg-[repeating-linear-gradient(to_right,transparent_0,transparent_calc(var(--tree-indent)-1px),var(--border)_calc(var(--tree-indent)-1px),var(--border)_calc(var(--tree-indent)))]" 
      indent={indent} 
      tree={tree}
    >
      {tree.getItems().map((item) => {
        return (
          <TreeItem item={item} key={item.getId()} className="w-full">
            <TreeItemLabel className="bg-transparent before:-inset-y-0.5 before:-z-10 relative before:absolute before:inset-x-0 before:bg-sidebar hover:bg-gray-200 
     in-data-[selected=true]:bg-gray-200 px-2 w-full">
              <span className="flex items-center gap-2 min-w-0">
                {/* {item.isFolder() &&
                  (item.isExpanded() ? (
                    <FolderOpenIcon className="pointer-events-none size-4 text-muted-foreground" />
                  ) : (
                    <FolderIcon className="pointer-events-none size-4 text-muted-foreground" />
                  ))} */}
                <span className="truncate">
                  {item.getItemName()}
                </span>
                {item.isFolder() && (
                  <span className="-ms-1 text-muted-foreground shrink-0">
                    {`(${item.getChildren().length})`}
                  </span>
                )}
              </span>
            </TreeItemLabel>
          </TreeItem>
        );
      })}
    </Tree>
  );
}