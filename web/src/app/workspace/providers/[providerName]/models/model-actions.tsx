'use client';

import {
  LlmProvider,
  LlmProviderModel,
  LlmProviderModelCreateApiEnum,
} from '@/api';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { apiClient } from '@/lib/api/client';
import { zodResolver } from '@hookform/resolvers/zod';
import { Slot } from '@radix-ui/react-slot';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';

import { toast } from 'sonner';
import * as z from 'zod';

const defaultValue = {
  model: '',
  api: LlmProviderModelCreateApiEnum.completion,
};

const modelSchema = z.object({
  model: z.string().min(1),
  api: z.string().min(1),
  context_window: z.coerce.number<number>().optional(),
  max_input_tokens: z.coerce.number<number>().optional(),
  max_output_tokens: z.coerce.number<number>().optional(),
});

export const ModelActions = ({
  model,
  provider,
  action,
  children,
}: {
  provider: LlmProvider;
  model?: LlmProviderModel;
  action: 'add' | 'edit' | 'delete';
  children?: React.ReactNode;
}) => {
  const page_models = useTranslations('page_models');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');

  const [createOrUpdateVisible, setCreateOrUpdateVisible] =
    useState<boolean>(false);
  const [deleteVisible, setDeleteVisible] = useState<boolean>(false);
  const router = useRouter();

  const form = useForm<z.infer<typeof modelSchema>>({
    resolver: zodResolver(modelSchema),
    defaultValues: { ...defaultValue, ...model },
  });

  const handleDelete = useCallback(async () => {
    if (action === 'delete' && model?.model) {
      const res =
        await apiClient.defaultApi.llmProvidersProviderNameModelsApiModelDelete(
          {
            providerName: provider.name,
            api: model.api,
            model: model.model,
          },
        );
      if (res?.status === 200) {
        setDeleteVisible(false);
        setTimeout(router.refresh, 300);
      }
    }
  }, [action, model?.api, model?.model, provider.name, router]);

  const handleCreateOrUpdate = useCallback(
    async (values: z.infer<typeof modelSchema>) => {
      let res;
      if (action === 'edit' && model?.model) {
        res =
          await apiClient.defaultApi.llmProvidersProviderNameModelsApiModelPut({
            providerName: provider.name,
            api: model.api,
            model: model.model,
            llmProviderModelUpdate: {
              custom_llm_provider: provider.name,
              context_window: values.context_window,
              max_input_tokens: values.max_input_tokens,
              max_output_tokens: values.max_output_tokens,
            },
          });
      }
      if (action === 'add') {
        res = await apiClient.defaultApi.llmProvidersProviderNameModelsPost({
          providerName: provider.name,
          llmProviderModelCreate: {
            provider_name: provider.name,
            api: values.api as LlmProviderModelCreateApiEnum,
            model: values.model,
            custom_llm_provider: provider.name,
            context_window: values.context_window,
            max_input_tokens: values.max_input_tokens,
            max_output_tokens: values.max_output_tokens,
          },
        });
      }
      if (res?.status === 200) {
        setCreateOrUpdateVisible(false);
        setTimeout(router.refresh, 300);
        toast.success(common_tips('save_success'));
      }
    },
    [
      action,
      common_tips,
      model?.api,
      model?.model,
      provider.name,
      router.refresh,
    ],
  );

  if (action === 'delete') {
    return (
      <Dialog open={deleteVisible} onOpenChange={() => setDeleteVisible(false)}>
        <DialogTrigger asChild>
          <Slot
            onClick={(e) => {
              setDeleteVisible(true);
              e.preventDefault();
            }}
          >
            {children}
          </Slot>
        </DialogTrigger>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{common_tips('confirm')}</DialogTitle>
            <DialogDescription>
              {page_models('model.delete_confirm')}
            </DialogDescription>
          </DialogHeader>
          <DialogDescription></DialogDescription>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteVisible(false)}>
              {common_action('cancel')}
            </Button>
            <Button variant="destructive" onClick={() => handleDelete()}>
              {common_action('continue')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  } else {
    return (
      <Dialog
        open={createOrUpdateVisible}
        onOpenChange={() => setCreateOrUpdateVisible(false)}
      >
        <DialogTrigger asChild>
          <Slot
            onClick={(e) => {
              setCreateOrUpdateVisible(true);
              e.preventDefault();
            }}
          >
            {children}
          </Slot>
        </DialogTrigger>
        <DialogContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleCreateOrUpdate)}
              className="space-y-8"
            >
              <DialogHeader>
                <DialogTitle>
                  {action === 'add' && page_models('model.add_model')}
                  {action === 'edit' && page_models('model.edit_model')}
                </DialogTitle>
                <DialogDescription></DialogDescription>
              </DialogHeader>
              <FormField
                control={form.control}
                name="model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{page_models('model.name')}</FormLabel>
                    <FormControl>
                      <Input
                        disabled={model !== undefined}
                        placeholder={page_models('model.name_placeholder')}
                        {...field}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="api"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{page_models('model.api_type')}</FormLabel>
                    <FormControl>
                      <RadioGroup
                        className="grid grid-cols-3 gap-4"
                        onValueChange={field.onChange}
                        disabled={model !== undefined}
                        {...field}
                      >
                        <div className="bg-card flex h-9 items-center gap-3 rounded-md border px-3">
                          <RadioGroupItem
                            value={LlmProviderModelCreateApiEnum.completion}
                            id="completion"
                          />
                          <Label
                            htmlFor="completion"
                            className={
                              model == undefined ? '' : 'text-muted-foreground'
                            }
                          >
                            Completion
                          </Label>
                        </div>
                        <div className="bg-card flex h-9 items-center gap-3 rounded-md border px-3">
                          <RadioGroupItem
                            value={LlmProviderModelCreateApiEnum.embedding}
                            id="embedding"
                          />
                          <Label
                            htmlFor="embedding"
                            className={
                              model == undefined ? '' : 'text-muted-foreground'
                            }
                          >
                            Embedding
                          </Label>
                        </div>
                        <div className="bg-card flex h-9 items-center gap-3 rounded-md border px-3">
                          <RadioGroupItem
                            value={LlmProviderModelCreateApiEnum.rerank}
                            id="rerank"
                          />
                          <Label
                            htmlFor="rerank"
                            className={
                              model == undefined ? '' : 'text-muted-foreground'
                            }
                          >
                            Rerank
                          </Label>
                        </div>
                      </RadioGroup>
                    </FormControl>
                  </FormItem>
                )}
              />
              <div>
                <FormLabel className="text-muted-foreground mb-4">
                  {page_models('model.llm_params')}
                </FormLabel>
                <div className="grid grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="context_window"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Context Window</FormLabel>
                        <FormControl>
                          <Input {...field} type="number" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="max_input_tokens"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Max Input Tokens</FormLabel>
                        <FormControl>
                          <Input {...field} type="number" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="max_output_tokens"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Max Output Tokens</FormLabel>
                        <FormControl>
                          <Input {...field} type="number" />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreateOrUpdateVisible(false)}
                >
                  {common_action('cancel')}
                </Button>
                <Button type="submit">{common_action('save')}</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    );
  }
};
