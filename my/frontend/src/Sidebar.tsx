
import * as React from "react"
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
} from "@/components/ui/sidebar"
import { Separator } from "@radix-ui/react-separator"
import { ScrollArea } from "@/components/ui/scroll-area";
import { TaskFinder } from './TaskFinder';

export function AppSidebar({ selectedExp, selectedTask, onSelect, ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader className="!px-4 !h-12">
        <div className="h-full flex w-full items-center">
          <a className="text-md font-semibold">
            Runs
          </a>
        </div>
      </SidebarHeader>
      <Separator />
      <SidebarContent className="px-1.5">
        <TaskFinder onSelect={onSelect} selectedExp={selectedExp} selectedTask={selectedTask} />
      </SidebarContent>
    </Sidebar>
  )
}
