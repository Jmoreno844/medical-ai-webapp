import * as React from "react";
import { CalendarIcon } from "lucide-react";
import { format } from "date-fns";

import { cn } from "@/lib/utils";
import { Button } from "@/commons/components/ui/button";
import { Calendar } from "@/commons/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/commons/components/ui/popover";
import { ScrollArea, ScrollBar } from "@/commons/components/ui/scroll-area";

interface DateTimePickerProps {
  value?: Date;
  onChange?: (date: Date) => void;
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function DateTimePicker({
  value,
  onChange,
  isOpen: controlledIsOpen,
  onOpenChange,
}: DateTimePickerProps) {
  // Initialize state with value prop if available
  const [date, setDate] = React.useState<Date | undefined>(value);
  const [isOpenState, setIsOpenState] = React.useState(false);

  // Always use the value prop if it's provided
  const currentDate = value || date;

  const isOpen =
    controlledIsOpen !== undefined ? controlledIsOpen : isOpenState;
  const setIsOpen = (open: boolean) => {
    setIsOpenState(open);
    if (onOpenChange) {
      onOpenChange(open);
    }
  };

  // Keep internal state in sync with value prop
  React.useEffect(() => {
    if (value) {
      setDate(value);
    }
  }, [value]);

  const hours = Array.from({ length: 12 }, (_, i) => i + 1);

  const handleDateSelect = (selectedDate: Date | undefined) => {
    if (!selectedDate) return;

    const newDate = new Date(selectedDate);

    if (currentDate) {
      newDate.setHours(currentDate.getHours());
      newDate.setMinutes(currentDate.getMinutes());
      newDate.setSeconds(currentDate.getSeconds());
    }

    setDate(newDate);
    if (onChange) onChange(newDate);
  };

  const handleTimeChange = (
    type: "hour" | "minute" | "ampm",
    value: string,
    e: React.MouseEvent<HTMLButtonElement>
  ) => {
    // Prevent the click from bubbling up and closing the popover
    e.stopPropagation();

    if (!currentDate) {
      const newDate = new Date();
      setDate(newDate);

      updateTimeComponent(newDate, type, value);
      if (onChange) {
        // Don't close the popover when calling onChange
        onChange(newDate);
      }
      return;
    }

    const newDate = new Date(currentDate);
    updateTimeComponent(newDate, type, value);
    setDate(newDate);
    if (onChange) {
      // Don't close the popover when calling onChange
      onChange(newDate);
    }
  };

  const updateTimeComponent = (
    dateToUpdate: Date,
    type: "hour" | "minute" | "ampm",
    value: string
  ) => {
    if (type === "hour") {
      dateToUpdate.setHours(
        (parseInt(value) % 12) + (dateToUpdate.getHours() >= 12 ? 12 : 0)
      );
    } else if (type === "minute") {
      dateToUpdate.setMinutes(parseInt(value));
    } else if (type === "ampm") {
      const currentHours = dateToUpdate.getHours();
      const isPM = currentHours >= 12;
      if (value === "PM" && !isPM) {
        dateToUpdate.setHours(currentHours + 12);
      } else if (value === "AM" && isPM) {
        dateToUpdate.setHours(currentHours - 12);
      }
    }
  };

  const isHourSelected = (hour: number): boolean => {
    return (
      !!currentDate &&
      (currentDate.getHours() % 12 === hour % 12 ||
        (hour === 12 && currentDate.getHours() % 12 === 0))
    );
  };

  const isMinuteSelected = (minute: number): boolean => {
    if (!currentDate) return false;
    // Only highlight if it's exactly the same minute (only for 5-minute increments)
    return currentDate.getMinutes() === minute;
  };

  // Helper to check if the minute is a multiple of 5
  const isExactFiveMinuteIncrement = (minutes: number): boolean => {
    return minutes % 5 === 0;
  };

  // Get the exact minute value if it's not a multiple of 5
  const getExactMinute = (): number | null => {
    if (!currentDate) return null;
    const minutes = currentDate.getMinutes();
    return isExactFiveMinuteIncrement(minutes) ? null : minutes;
  };

  const isAMPMSelected = (ampm: string): boolean => {
    if (!currentDate) return false;
    return (
      (ampm === "AM" && currentDate.getHours() < 12) ||
      (ampm === "PM" && currentDate.getHours() >= 12)
    );
  };

  const selectedStyle =
    "bg-purple-500 text-white font-bold  ring-purple-900 shadow-md border-black";

  const timeButtonStyle =
    "h-9 w-9 p-0 font-normal text-sm rounded-md flex items-center justify-center m-1";

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "w-full justify-start text-left font-normal",
            !currentDate && "text-muted-foreground"
          )}
          // Prevent any unexpected click behavior
          onClick={(e) => {
            e.stopPropagation();
            setIsOpen(!isOpen);
          }}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {/* Force evaluation of currentDate to trigger render */}
          {currentDate instanceof Date ? (
            format(currentDate, "dd/MM/yyyy HH:mm")
          ) : (
            <span>DD/MM/YYYY HH:MM</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-auto p-0 bg-white border shadow-md"
        side="bottom"
        align="start"
        alignOffset={0}
        avoidCollisions={false}
      >
        <div className="sm:flex bg-white">
          <Calendar
            mode="single"
            selected={currentDate}
            onSelect={handleDateSelect}
            initialFocus
            className="bg-white"
            classNames={{
              day_selected:
                "bg-purple-500 text-white font-bold hover:bg-purple-400 ring-purple-300",
              day_today: "bg-accent text-accent-foreground",
            }}
          />
          <div className="flex flex-col sm:flex-row sm:h-[300px] divide-y sm:divide-y-0 sm:divide-x bg-white">
            <ScrollArea className="w-64 sm:w-auto">
              <div className="flex flex-wrap sm:flex-col p-2 justify-center">
                {hours.map((hour) => (
                  <Button
                    key={hour}
                    variant={isHourSelected(hour) ? "default" : "ghost"}
                    className={cn(
                      timeButtonStyle,
                      isHourSelected(hour) && selectedStyle
                    )}
                    onClick={(e) =>
                      handleTimeChange("hour", hour.toString(), e)
                    }
                  >
                    {hour}
                  </Button>
                ))}
              </div>
              <ScrollBar orientation="horizontal" className="sm:hidden" />
            </ScrollArea>
            <ScrollArea className="w-64 sm:w-auto">
              <div className="flex flex-wrap sm:flex-col p-2 justify-center">
                {/* Use a function to create and order the buttons */}
                {(() => {
                  const exactMinute = getExactMinute();
                  const buttons = [];

                  // For each 5-minute increment
                  for (let i = 0; i < 12; i++) {
                    const minute = i * 5;

                    // Add the standard 5-minute increment button
                    buttons.push(
                      <Button
                        key={`min-${minute}`}
                        variant={isMinuteSelected(minute) ? "default" : "ghost"}
                        className={cn(
                          timeButtonStyle,
                          isMinuteSelected(minute) && selectedStyle
                        )}
                        onClick={(e) =>
                          handleTimeChange("minute", minute.toString(), e)
                        }
                      >
                        {minute < 10 ? `0${minute}` : minute}
                      </Button>
                    );

                    // If our exact minute falls between this and the next increment, insert it
                    if (
                      exactMinute !== null &&
                      exactMinute > minute &&
                      exactMinute < (i === 11 ? 60 : (i + 1) * 5)
                    ) {
                      buttons.push(
                        <Button
                          key={`exact-${exactMinute}`}
                          variant="default"
                          className={cn(
                            timeButtonStyle,
                            "bg-purple-500 text-white font-semibold border border-purple-300"
                          )}
                          onClick={(e) => {
                            /* Already selected */
                            e.stopPropagation();
                          }}
                        >
                          {exactMinute < 10 ? `0${exactMinute}` : exactMinute}
                        </Button>
                      );
                    }
                  }

                  return buttons;
                })()}
              </div>
              <ScrollBar orientation="horizontal" className="sm:hidden" />
            </ScrollArea>
            <ScrollArea className="">
              <div className="flex flex-wrap sm:flex-col p-2 justify-center">
                {["AM", "PM"].map((ampm) => (
                  <Button
                    key={ampm}
                    variant={isAMPMSelected(ampm) ? "default" : "ghost"}
                    className={cn(
                      timeButtonStyle,
                      isAMPMSelected(ampm) && selectedStyle
                    )}
                    onClick={(e) => handleTimeChange("ampm", ampm, e)}
                  >
                    {ampm}
                  </Button>
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
