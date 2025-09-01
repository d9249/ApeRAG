'use client';

import { ApiKey } from '@/api';
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
  FormDescription,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api/client';
import { zodResolver } from '@hookform/resolvers/zod';
import { Slot } from '@radix-ui/react-slot';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useState } from 'react';
import { useForm } from 'react-hook-form';
import * as z from 'zod';

const apiKeySchema = z.object({
  description: z.string(),
});

export const ApiKeyActions = ({
  apiKey,
  action,
  children,
}: {
  apiKey?: ApiKey;
  action: 'add' | 'edit' | 'delete';
  children?: React.ReactNode;
}) => {
  const page_api_keys = useTranslations('page_api_keys');
  const common_action = useTranslations('common.action');
  const common_tips = useTranslations('common.tips');
  const [createOrUpdateVisible, setCreateOrUpdateVisible] =
    useState<boolean>(false);
  const [deleteVisible, setDeleteVisible] = useState<boolean>(false);
  const router = useRouter();
  const form = useForm<z.infer<typeof apiKeySchema>>({
    resolver: zodResolver(apiKeySchema),
    defaultValues: {
      description: apiKey?.description || '',
    },
  });

  const handleCreateOrUpdate = useCallback(
    async (values: z.infer<typeof apiKeySchema>) => {
      let res;
      if (action === 'edit' && apiKey?.id) {
        res = await apiClient.defaultApi.apikeysApikeyIdPut({
          apikeyId: apiKey.id,
          apiKeyUpdate: values,
        });
      }
      if (action === 'add') {
        res = await apiClient.defaultApi.apikeysPost({
          apiKeyCreate: values,
        });
      }
      if (res?.status === 200) {
        setCreateOrUpdateVisible(false);
        setTimeout(router.refresh, 300);
      }
    },
    [action, apiKey?.id, router],
  );

  const handleDelete = useCallback(async () => {
    if (action === 'delete' && apiKey?.id) {
      const res = await apiClient.defaultApi.apikeysApikeyIdDelete({
        apikeyId: apiKey.id,
      });
      if (res?.status === 200) {
        setDeleteVisible(false);
        setTimeout(router.refresh, 300);
      }
    }
  }, [action, apiKey?.id, router]);

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
              {page_api_keys('delete_api_key_confirm')}
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
        <DialogContent showCloseButton={false}>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(handleCreateOrUpdate)}
              className="space-y-8"
            >
              <DialogHeader>
                <DialogTitle>API Key</DialogTitle>
                <DialogDescription></DialogDescription>
              </DialogHeader>
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormControl>
                      <Textarea
                        placeholder={page_api_keys('api_key_placeholder')}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {page_api_keys('api_key_description')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
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
