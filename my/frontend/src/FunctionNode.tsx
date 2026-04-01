
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { Position, Handle } from '@xyflow/react';

export function FunctionNode(props) {
  const { data } = props;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="outline">
          {data.label}
          <Handle type="source" position={Position.Bottom} />
          <Handle type="target" position={Position.Top} />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>{data.info.name}</p>
      </TooltipContent>
    </Tooltip>
  );
}