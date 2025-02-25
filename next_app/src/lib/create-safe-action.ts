import { z } from "zod";

export type FieldErrors<T> = {
  [K in keyof T]?: string[];
};

export interface ActionState<TInput, TOutput> {
  fieldErrors?: FieldErrors<TInput>;
  error?: string | null;
  data?: TOutput;
}

export const createSafeAction = <TInput, TOutput>(
  handler: (data: TInput) => Promise<ActionState<TInput, TOutput>>
) => {
  return async (data: TInput): Promise<ActionState<TInput, TOutput>> => {
    try {
      return await handler(data);
    } catch (error) {
      return {
        error: error instanceof Error ? error.message : "Something went wrong!",
      };
    }
  };
};
