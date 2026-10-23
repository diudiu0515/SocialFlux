'use client';
import type {ComponentPropsWithRef} from 'react';
import {mediaRetired} from '../lib/retired-media';

export function MediaVideo(props: ComponentPropsWithRef<'video'>) {
  if (typeof props.src === 'string' && mediaRetired(props.src)) return <p className="notice">这段旧版视频已清理。原题目与标注记录保留；无法核实视频时请选择无法判断，或保存后进入新版入口。</p>;
  return <video {...props}/>;
}
