import Image from "next/image";
import { HTMLAttributes } from "react";

interface IconProps extends HTMLAttributes<HTMLDivElement> {
  src?: string;
  alt?: string;
  size?: number;
}

const Icon = ({
  src = "/home_icon.svg",
  alt = "icon",
  size = 24,
  className,
  ...props
}: IconProps) => (
  <div {...props} className={className}>
    <Image src={src} alt={alt} width={size} height={size} />
  </div>
);

export default Icon;
