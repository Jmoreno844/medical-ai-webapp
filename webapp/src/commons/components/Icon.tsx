import React from "react";

interface IconProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string;
  alt?: string;
  size?: number;
}

const Icon: React.FC<IconProps> = ({
  src = "/home_icon.svg",
  alt = "icon",
  size = 24,
  className,
  ...props
}) => {
  return (
    <div {...props} className={className}>
      <img src={src} alt={alt} width={size} height={size} />
    </div>
  );
};

export default Icon;
