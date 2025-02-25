import { ButtonHTMLAttributes } from "react";
import Icon from "./icons/Icon";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  src: string;
  alt?: string;
  size?: number;
}

const IconButton = ({
  src,
  alt,
  size,
  className,
  ...props
}: IconButtonProps) => {
  return (
    <button
      type="button"
      className={`p-1 rounded-full hover:bg-gray-100 transition-colors ${className}`}
      {...props}
    >
      <Icon src={src} alt={alt} size={size} />
    </button>
  );
};

export default IconButton;
