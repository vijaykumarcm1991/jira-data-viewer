import { useEffect, useState } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Plus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { FieldDef } from "@/types/jira";

interface FieldSelectorProps {
  fields: FieldDef[];
  selected: string[];
  onChange: (next: string[]) => void;
}

export function FieldSelector({ fields, selected, onChange }: FieldSelectorProps) {
  const [search, setSearch] = useState("");
  const selectedSet = new Set(selected);
  const available = fields.filter(
    (f) => !selectedSet.has(f.id) && f.name.toLowerCase().includes(search.toLowerCase())
  );
  const selectedFields = selected
    .map((id) => fields.find((c) => c.id === id))
    .filter((f): f is FieldDef => Boolean(f));

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIdx = selected.indexOf(String(active.id));
    const newIdx = selected.indexOf(String(over.id));
    if (oldIdx < 0 || newIdx < 0) return;
    onChange(arrayMove(selected, oldIdx, newIdx));
  };

  const addField = (id: string) => onChange([...selected, id]);
  const removeField = (id: string) => onChange(selected.filter((x) => x !== id));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="border rounded-lg p-3 flex flex-col min-h-[320px]">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium">Available fields</h4>
          <span className="text-xs text-muted-foreground">{available.length}</span>
        </div>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search…"
          className="mb-2"
        />
        <ScrollArea className="flex-1 max-h-[420px]">
          <div className="space-y-1 pr-2">
            {available.length === 0 && (
              <p className="text-xs text-muted-foreground p-2 text-center">No more fields</p>
            )}
            {available.map((f) => (
              <div
                key={f.id}
                className="flex items-center justify-between text-sm border rounded-md px-2 py-1.5 bg-card hover:bg-accent"
              >
                <div>
                  <div className="font-medium">{f.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {f.type}
                    {f.is_custom ? " · custom" : ""}
                    {f.schema_type ? ` · ${f.schema_type}` : ""}
                  </div>
                </div>
                <Button size="icon" variant="ghost" onClick={() => addField(f.id)} aria-label="Add">
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>

      <div className="border rounded-lg p-3 flex flex-col min-h-[320px]">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium">Selected fields (drag to reorder)</h4>
          <span className="text-xs text-muted-foreground">{selected.length}</span>
        </div>
        <ScrollArea className="flex-1 max-h-[420px]">
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={selected} strategy={verticalListSortingStrategy}>
              <div className="space-y-1 pr-2">
                {selected.length === 0 && (
                  <p className="text-xs text-muted-foreground p-2 text-center">
                    Add at least one field from the left.
                  </p>
                )}
                {selectedFields.map((f) => (
                  <SortableRow key={f.id} field={f} onRemove={() => removeField(f.id)} />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        </ScrollArea>
      </div>
    </div>
  );
}

function SortableRow({ field, onRemove }: { field: FieldDef; onRemove: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: field.id,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex items-center justify-between text-sm border rounded-md px-2 py-1.5 bg-primary/5",
        isDragging && "opacity-60 ring-2 ring-primary/30"
      )}
    >
      <div className="flex items-center gap-2">
        <button
          type="button"
          {...attributes}
          {...listeners}
          className="cursor-grab text-muted-foreground hover:text-foreground"
          aria-label="Drag to reorder"
        >
          <GripVertical className="h-4 w-4" />
        </button>
        <div>
          <div className="font-medium">{field.name}</div>
          <div className="text-xs text-muted-foreground">
            {field.type}
            {field.is_custom ? " · custom" : ""}
            {field.schema_type ? ` · ${field.schema_type}` : ""}
          </div>
        </div>
      </div>
      <Button size="icon" variant="ghost" onClick={onRemove} aria-label="Remove">
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}
