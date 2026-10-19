import { Select } from "@base-ui/react/select";
import { Tabs } from "@base-ui/react/tabs";
import { Accordion } from "@base-ui/react/accordion";
import { Checkbox } from "@base-ui/react/checkbox";
import { Slider } from "@base-ui/react/slider";
import { Button } from "@base-ui/react/button";
import type { ComponentProps, ReactNode } from "react";

export function BaseButton(props: ComponentProps<typeof Button>) {
  return <Button {...props} />;
}

export function BaseSelect({ label, value, onChange, options, ariaLabel }: { label?: string; value: string; onChange: (value: string) => void; options: { value: string; label: string }[]; ariaLabel?: string }) {
  return <Select.Root items={options} value={value} onValueChange={(next) => next != null && onChange(next)}>
    {label && <Select.Label className="base-label">{label}</Select.Label>}
    <Select.Trigger className="base-select-trigger" aria-label={ariaLabel || label}>
      <Select.Value /> <Select.Icon>⌄</Select.Icon>
    </Select.Trigger>
    <Select.Portal><Select.Positioner className="base-select-positioner" sideOffset={5} alignItemWithTrigger={false}><Select.Popup className="base-select-popup"><Select.List>{options.map(option => <Select.Item key={option.value} value={option.value} className="base-select-item"><Select.ItemText>{option.label}</Select.ItemText><Select.ItemIndicator>✓</Select.ItemIndicator></Select.Item>)}</Select.List></Select.Popup></Select.Positioner></Select.Portal>
  </Select.Root>;
}

export function BaseTabs({ value, onChange, items }: { value: string; onChange: (value: string) => void; items: { value: string; label: ReactNode }[] }) {
  return <Tabs.Root className="base-tabs" value={value} onValueChange={(next) => next != null && onChange(String(next))}>
    <Tabs.List className="base-tabs-list">{items.map(item => <Tabs.Tab key={item.value} value={item.value} className="base-tab">{item.label}</Tabs.Tab>)}<Tabs.Indicator className="base-tabs-indicator" /></Tabs.List>
  </Tabs.Root>;
}

export function BaseAccordion({ title, children }: { title: string; children: ReactNode }) {
  return <Accordion.Root className="base-accordion"><Accordion.Item value="settings" className="base-accordion-item"><Accordion.Header><Accordion.Trigger className="base-accordion-trigger">{title}<span>⌄</span></Accordion.Trigger></Accordion.Header><Accordion.Panel className="base-accordion-panel">{children}</Accordion.Panel></Accordion.Item></Accordion.Root>;
}

export function BaseCheckbox({ checked, onChange, children, required = false }: { checked: boolean; onChange: (checked: boolean) => void; children: ReactNode; required?: boolean }) {
  return <label className="cs-check base-checkbox-label"><Checkbox.Root className="base-checkbox" checked={checked} required={required} onCheckedChange={(next) => onChange(next === true)}><Checkbox.Indicator>✓</Checkbox.Indicator></Checkbox.Root>{children}</label>;
}

export function BaseSlider({ value, onChange, min = 0, max = 1, step = 0.1, ariaLabel }: { value: number; onChange: (value: number) => void; min?: number; max?: number; step?: number; ariaLabel: string }) {
  return <Slider.Root className="base-slider" value={[value]} min={min} max={max} step={step} onValueChange={(next) => onChange(Array.isArray(next) ? Number(next[0]) : value)} aria-label={ariaLabel}><Slider.Control className="base-slider-control"><Slider.Track className="base-slider-track"><Slider.Indicator className="base-slider-indicator" /><Slider.Thumb className="base-slider-thumb" /></Slider.Track></Slider.Control></Slider.Root>;
}
